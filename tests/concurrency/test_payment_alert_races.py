"""VS-024 alert race on real Postgres (plan 3.5): two late captures of one payment meet at
the first lock (`orders FOR UPDATE`); the payment is recorded late-captured once and every
active administrator gets exactly one notification and one email."""

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.identity.public import active_administrator_contacts
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import verify_event, verify_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.test_payment_races import STAGGER, _as, _factory, _synced_locks
from tests.integration.deep_support import create_user
from tests.integration.payments.test_verification import _event
from tests.integration.payments.verification_support import (
    mock_fixture,  # noqa: F401
    pending_payment,
)

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app"),
]

STATE = """
    SELECT p.status, p.captured_amount_cents,
      (SELECT count(*) FROM audit_logs WHERE entity_id = p.id
         AND action = 'payment.late_capture') AS late_audits,
      (SELECT count(*) FROM audit_logs WHERE entity_id = p.id
         AND action = 'payment.alert_raised') AS alerts
    FROM payments p WHERE p.id = :p
"""
PER_ADMIN = """
    SELECT u.id,
      (SELECT count(*) FROM notifications n WHERE n.user_id = u.id
         AND n.payload->>'payment_id' = CAST(:p AS text)) AS notifications,
      (SELECT count(*) FROM email_outbox e WHERE e.user_id = u.id
         AND e.template = 'admin_payment_alert'
         AND e.payload->>'payment_id' = CAST(:p AS text)) AS emails
    FROM users u WHERE u.id = ANY(:admins)
"""


@pytest.mark.parametrize("first", ["webhook", "reconcile"])
async def test_two_late_captures_at_once_alert_each_admin_exactly_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    await create_user(db_session, role=UserRole.ADMIN)
    admins = [admin_id for admin_id, _ in await active_administrator_contacts(db_session)]
    await db_session.commit()
    seeded = await pending_payment(db_session, mock, total_cents=1000)
    await mock.simulate(seeded.payment_id, "paid", 900)
    event_id = await _event(db_engine, seeded)
    _synced_locks(monkeypatch, seeded.order_id, 2)
    factory, providers = _factory(db_engine), {"mock": mock}

    async def webhook() -> Any:
        return await verify_event(factory, providers, event_id)

    async def reconcile() -> Any:
        return await verify_payment(factory, providers, seeded.payment_id)

    webhook_delay, reconcile_delay = (0.0, STAGGER) if first == "webhook" else (STAGGER, 0.0)
    outcomes = await asyncio.gather(_as(webhook_delay, webhook), _as(reconcile_delay, reconcile))
    assert sorted(outcomes) == sorted([Outcome.LATE_CAPTURE_AND_FAIL, Outcome.NOOP]), outcomes
    async with db_engine.connect() as conn:
        state = (await conn.execute(text(STATE), {"p": seeded.payment_id})).one()
        per_admin = (
            await conn.execute(text(PER_ADMIN), {"p": str(seeded.payment_id), "admins": admins})
        ).all()
    print(f"\nRACE first={first}: {outcomes}, {state}, admins={len(per_admin)}")
    assert (state.status, state.captured_amount_cents) == ("failed", 900)
    assert (state.late_audits, state.alerts) == (1, 1)
    assert len(per_admin) == len(admins) >= 2
    assert all((row.notifications, row.emails) == (1, 1) for row in per_admin), per_admin
