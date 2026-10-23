"""S2 (VS-030 plan 6.5): no refund or chargeback response, audit row, outbox payload,
notification or log line carries the contact phone, its hash, the address or the payment's
provider reference; the dispute reference stays on the chargeback record itself."""

import io
import json
import logging
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import hash_phone
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, mfa_admin
from tests.integration.payments.refund_support import (
    act,
    chargeback,
    create,
    ok,
    paid_online,
    payment_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

DISPUTE = "dp-sentinel-7731"


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Every handler the app configures writes into this buffer, through its formatter."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    return buffer


async def test_s2_refund_and_chargeback_records_never_leak(
    db_engine: AsyncEngine, db_session: AsyncSession, app_logs: io.StringIO
) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    payment = await payment_of(db_engine, order.order_id)
    responses: list[object] = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        first = ok(create(client, order.order_id, [(a, 100)]), 201)
        responses.append(first)
        responses.append(ok(act(client, first["id"], "fail", {"reason": "Bounced."})))
        twin = ok(act(client, first["id"], "reissue"), 201)
        responses += [twin, ok(act(client, twin["id"], "settle", {"reference": "dash-1"}))]
        second = ok(create(client, order.order_id, [(b, 100)]), 201)
        responses += [second, ok(act(client, second["id"], "void", {"reason": "Twice."}))]
        responses.append(
            ok(chargeback(client, order.order_id, payment, 500, [(b, 400)], dispute=DISPUTE), 201)
        )
    async with db_engine.connect() as conn:
        written = (
            await conn.execute(
                text(
                    "SELECT before_data, after_data FROM audit_logs WHERE entity_id IN"
                    " (SELECT id FROM refunds WHERE order_id = :o"
                    "  UNION SELECT id FROM chargebacks WHERE order_id = :o)"
                    " OR after_data->>'order_id' = CAST(:o AS text)"
                    " UNION ALL SELECT payload, NULL FROM email_outbox"
                    " WHERE payload->>'order_id' = CAST(:o AS text)"
                    " UNION ALL SELECT payload, NULL FROM notifications"
                    " WHERE payload->>'order_id' = CAST(:o AS text)"
                ),
                {"o": order.order_id},
            )
        ).all()
        reference = await conn.scalar(
            text("SELECT provider_payment_id FROM payments WHERE id = :p"), {"p": payment}
        )
    stored = json.dumps([list(row) for row in written], default=str)
    shown = json.dumps(responses, default=str)
    logs = app_logs.getvalue()
    assert written, "the scan must see the rows it checks"
    for secret in (order.phone, hash_phone(order.phone), str(reference), "Zahle", "Blue door"):
        for where, haystack in (("stored", stored), ("responses", shown), ("logs", logs)):
            assert secret not in haystack, (secret, where)
    assert DISPUTE not in stored and DISPUTE not in logs  # only on the chargeback record
    assert str(uuid.UUID(first["id"])) in stored
