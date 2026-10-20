"""VS-024 security (plan 6.5): no route, even an MFA administrator's, marks a mock payment
paid; the new routes' responses never carry provider metadata, a webhook payload or
secret, or the customer's email; the confirm and release reasons are never logged."""

import io
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.routing import iter_route_contexts
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.main import app as main_app
from app.payments.application.ports import PaymentRef
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, csrf, login, mfa_admin
from tests.integration.payments.recovery_support import (
    HOLD,
    drop_alert_emails,  # noqa: F401
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import NoStatus
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

GRACE = timedelta(hours=24)
EMAIL = "recovery-buyer@example.com"
REDIRECT = "https://pay.example/session-RECOVERY-SECURITY"
REASON_MARK = "REASON-TEXT-MARKER-"
NEW_PREFIXES = ("/api/v1/admin/payments", "/api/v1/admin/orders", "/api/v1/me/orders")
PROBE = {
    "payment_id": None,
    "status": "paid",
    "state": "paid",
    "verified_amount_cents": 1000,
    "verified_currency": "USD",
    "provider_reference": "dash_probe",
    "reason": "probe reason that is long enough",
    "events_reviewed": True,
}


CONFIRM = {
    "provider_reference": "dash_probe",
    "verified_amount_cents": 1000,
    "verified_currency": "USD",
    "reason": "dashboard shows a capture of 10.00 USD",
}


class QuietNoStatus(NoStatus):
    async def aclose(self) -> None:
        return None


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    return buffer


def _filled(path: str, payment_id: uuid.UUID, order_id: uuid.UUID) -> str:
    path = path.replace("{payment_id}", str(payment_id)).replace("{order_id}", str(order_id))
    return re.sub(r"\{[^}/]+(?::path)?\}", str(uuid.uuid4()), path)


async def test_no_route_reached_by_an_mfa_admin_marks_a_mock_payment_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Every route and method as an MFA administrator, with this payment and its order in
    the path and a body naming a capture: the mock still says pending, nothing is paid."""
    placed = datetime.now(UTC) - timedelta(minutes=5)
    order = await seed_order(db_session, placed_at=placed)
    payment_id = await seed_attempt(db_session, order, initiated_at=placed, mock=mock)
    routes = sorted(
        {
            (method, ctx.path)
            for ctx in iter_route_contexts(main_app.router.routes)
            for method in (ctx.methods or set())
            if ctx.path and method not in {"HEAD", "OPTIONS"}
        }
    )
    body = PROBE | {"payment_id": str(payment_id)}
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        for method, path in routes:
            if path.endswith(("/logout", "/refresh")):
                continue  # keep the admin's session for the rest of the walk
            client.request(
                method, _filled(path, payment_id, order.order_id), json=body, headers=csrf(client)
            )
    status = await mock.query_status(PaymentRef(payment_id, None))
    assert status.result.state == "pending"
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, verified_at FROM payments WHERE id = :p"), {"p": payment_id}
            )
        ).one()
    assert (row.status, row.verified_at) == ("pending", None)


async def test_the_new_routes_never_return_metadata_payloads_secrets_or_email(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer = await create_user(db_session, email=f"{uuid.uuid4().hex[:6]}-{EMAIL}")
    placed = datetime.now(UTC) - HOLD - GRACE - timedelta(minutes=5)
    order = await seed_order(
        db_session, placed_at=placed, user_id=buyer.id, customer_email_snapshot=buyer.email
    )
    payment_id = await seed_attempt(db_session, order, initiated_at=placed, mock=mock)
    await db_session.execute(
        text("UPDATE payments SET provider_metadata = CAST(:m AS jsonb) WHERE id = :p"),
        {"m": json.dumps({"redirect_url": REDIRECT}), "p": payment_id},
    )
    await db_session.commit()
    event = await seed_event(db_session, payment_id, received_at=placed)
    await db_session.execute(
        text("UPDATE webhook_events SET payload = CAST(:b AS jsonb) WHERE id = :e"),
        {"b": json.dumps({"note": "PAYLOAD-MARKER"}), "e": event},
    )
    await db_session.commit()
    secret = get_settings().mock_webhook_secret
    responses = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        responses.append(
            client.get("/api/v1/admin/payments", params={"order_id": str(order.order_id)})
        )
        responses.append(client.get(f"/api/v1/admin/payments/{payment_id}"))
        responses.append(
            client.post(f"/api/v1/admin/payments/{payment_id}/reconcile", headers=csrf(client))
        )
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        responses.append(
            client.post(
                f"/api/v1/admin/payments/{payment_id}/confirm",
                json=CONFIRM | {"verified_amount_cents": 999},
                headers=csrf(client),
            )
        )
        responses.append(
            client.post(
                f"/api/v1/admin/orders/{order.order_id}/release",
                json={"reason": "dashboard shows nothing at all", "events_reviewed": True},
                headers=csrf(client),
            )
        )
    assert [r.status_code for r in responses] == [200, 200, 202, 422, 200], [
        r.text for r in responses
    ]
    assert responses[3].json()["code"] == "PAYMENT_AMOUNT_MISMATCH"
    for response in responses:
        for forbidden in (
            REDIRECT,
            "provider_metadata",
            "PAYLOAD-MARKER",
            '"payload"',
            secret,
            buyer.email,
        ):
            assert forbidden not in response.text, (forbidden, response.request.url)


async def test_confirm_and_release_reasons_and_redirect_urls_never_reach_the_logs(
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    captured_logs: io.StringIO,
) -> None:
    placed = datetime.now(UTC) - HOLD - GRACE - timedelta(minutes=5)
    order = await seed_order(db_session, placed_at=placed)
    payment_id = await seed_attempt(
        db_session, order, initiated_at=placed, mock=mock, reference=False
    )
    other = await seed_order(db_session, placed_at=placed)
    await seed_attempt(db_session, other, initiated_at=placed, mock=mock)
    confirm_reason = f"{REASON_MARK}confirm-{uuid.uuid4().hex}"
    release_reason = f"{REASON_MARK}release-{uuid.uuid4().hex}"
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        refused = client.post(
            f"/api/v1/admin/payments/{payment_id}/confirm",
            json=CONFIRM | {"verified_amount_cents": 1, "reason": confirm_reason},
            headers=csrf(client),
        )
        confirmed = client.post(
            f"/api/v1/admin/payments/{payment_id}/confirm",
            json=CONFIRM
            | {"provider_reference": f"dash_{payment_id.hex}", "reason": confirm_reason},
            headers=csrf(client),
        )
        released = client.post(
            f"/api/v1/admin/orders/{other.order_id}/release",
            json={"reason": release_reason},
            headers=csrf(client),
        )
    with client_for(main_app) as client:
        owner = await create_user(db_session)
        mine = await seed_order(
            db_session, placed_at=datetime.now(UTC) - timedelta(minutes=5), user_id=owner.id
        )
        login(client, owner.email)
        retried = client.post(
            f"/api/v1/me/orders/{mine.order_id}/payments",
            json={},
            headers=csrf(client) | {"Idempotency-Key": f"sec-{uuid.uuid4().hex}"},
        )
    assert (refused.status_code, confirmed.status_code, released.status_code) == (422, 200, 200)
    assert retried.status_code == 201, retried.text
    logs = captured_logs.getvalue()
    assert "payment_manual_confirm_refused" in logs  # the refusal is logged, without the reason
    assert REASON_MARK not in logs
    assert retried.json()["payment"]["redirect_url"] not in logs
