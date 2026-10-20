"""The money risks of releasing an order whose payment later arrives (VS-024 plan 2.5,
R-a to R-g), on Postgres. Each: the released order and its lines stay untouched, the
capture is recorded with its amount, and every active admin is alerted exactly once."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.exceptions import ManualConfirmRefusedError
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_order_by_admin, release_stale
from app.payments.infrastructure.verification import verify_event, verify_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    PAYMENT_STATE,
    UNTOUCHED,
    YEARS_AHEAD,
    Down,
    SeededOrder,
    admin,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
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
NO_STATUS: Any = {"mock": NoStatus()}
PER_ADMIN = """
    SELECT
      (SELECT count(*) FROM notifications WHERE user_id = :u
         AND payload->>'event' = 'payment.alert.late_capture'
         AND payload->>'payment_id' = :p) AS notices,
      (SELECT count(*) FROM email_outbox WHERE user_id = :u AND template = 'admin_payment_alert'
         AND payload->>'kind' = 'late_capture' AND payload->>'payment_id' = :p) AS emails
"""


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 11, 1, tzinfo=UTC)


async def _alerted_once(
    engine: AsyncEngine, payment_id: uuid.UUID, admins: list[tuple[uuid.UUID, str]]
) -> None:
    assert admins
    for admin_id, _ in admins:
        row = await one(engine, PER_ADMIN, u=admin_id, p=str(payment_id))
        assert (row.notices, row.emails) == (1, 1), (admin_id, tuple(row))


async def _due(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, **kw: Any
) -> tuple[SeededOrder, uuid.UUID]:
    order = await seed_order(db, placed_at=at, **kw.pop("order", {}))
    return order, await seed_attempt(db, order, initiated_at=at, mock=mock, **kw)


async def _job_release(engine: AsyncEngine, providers: Any, at: datetime) -> dict[str, int]:
    return await release_stale(
        factory(engine), providers, now=at + timedelta(hours=1), start_after=keyset_start(at)
    )


async def _admin_release(
    engine: AsyncEngine, db: AsyncSession, order: SeededOrder, at: datetime, **kw: Any
) -> Any:
    admin_id = (await create_user(db, role=UserRole.ADMIN)).id
    async with async_sessionmaker(engine)() as session, session.begin():
        return await release_order_by_admin(
            session,
            order.order_id,
            admin_id=admin_id,
            reason="dashboard shows no payment; customer unreachable",
            events_reviewed=kw.get("events_reviewed", False),
            hold=HOLD,
            now=at + HOLD + GRACE,
        )


async def _event_verified(
    engine: AsyncEngine, db: AsyncSession, mock: MockPaymentProvider, payment_id: uuid.UUID
) -> Outcome | None:
    event_id = await seed_event(db, payment_id, received_at=datetime.now(UTC))
    return await verify_event(factory(engine), {"mock": mock}, event_id)


def _late(payment: Any, cents: int) -> None:
    assert payment.late_captured_at is not None, tuple(payment)
    assert (payment.captured_amount_cents, payment.captured_currency) == (cents, "USD")


async def test_late_success_after_automatic_release_is_a_late_capture(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-a: the provider said `expired`, the job released, the customer paid anyway."""
    at = epoch(1910)
    admins = await admin(db_session)
    order, payment_id = await _due(db_session, mock, at, state="expired")
    assert (await _job_release(db_engine, {"mock": mock}, at))["released"] == 1
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    await mock.simulate(payment_id, "paid")
    assert await _event_verified(db_engine, db_session, mock, payment_id) is Outcome.LATE_CAPTURE
    _late(await one(db_engine, PAYMENT_STATE, p=payment_id), 1000)
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "expired"
    assert await one(db_engine, ORDER_STATE, o=order.order_id) == released
    await _alerted_once(db_engine, payment_id, admins)


async def test_confirm_after_manual_release_records_late_capture_not_payment(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-b: no status API, a lost webhook; the admin confirms after releasing."""
    at = epoch(1911)
    admins = await admin(db_session)
    order, payment_id = await _due(db_session, mock, at, reference=False)
    await _admin_release(db_engine, db_session, order, at)
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    admin_id = (await create_user(db_session, role=UserRole.ADMIN)).id
    async with async_sessionmaker(db_engine)() as session, session.begin():
        outcome = await confirm_payment_manually(
            session,
            NO_STATUS,
            payment_id,
            admin_id=admin_id,
            provider_reference=f"dash_{payment_id.hex}",
            amount_cents=1000,
            currency="USD",
            reason="dashboard shows 10.00 USD captured after the release",
        )
    assert outcome is Outcome.LATE_CAPTURE
    _late(await one(db_engine, PAYMENT_STATE, p=payment_id), 1000)
    assert await one(db_engine, ORDER_STATE, o=order.order_id) == released
    await _alerted_once(db_engine, payment_id, admins)


async def test_release_with_reviewed_events_dismisses_them_and_a_later_event_is_a_late_capture(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-c: a dismissed event was a real payment; the next event for it is verified."""
    at = epoch(1912)
    admins = await admin(db_session)
    order, payment_id = await _due(db_session, mock, at)
    dismissed = await seed_event(db_session, payment_id, received_at=at)
    result = await _admin_release(db_engine, db_session, order, at, events_reviewed=True)
    assert result.events_dismissed == (dismissed,)
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    await mock.simulate(payment_id, "paid")
    assert await _event_verified(db_engine, db_session, mock, payment_id) is Outcome.LATE_CAPTURE
    _late(await one(db_engine, PAYMENT_STATE, p=payment_id), 1000)
    assert await one(db_engine, ORDER_STATE, o=order.order_id) == released
    await _alerted_once(db_engine, payment_id, admins)


async def test_rebuy_after_release_then_old_capture_leaves_new_order_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-d: the freed STL is bought again and paid; then the old session captures."""
    at = epoch(1913)
    admins = await admin(db_session)
    old, old_payment = await _due(db_session, mock, at, state="expired")
    assert (await _job_release(db_engine, {"mock": mock}, at))["released"] == 1
    new, new_payment = await _due(
        db_session,
        mock,
        at + timedelta(days=1),
        state="paid",
        order={"user_id": old.user_id, "stl_id": old.stl_id},
    )
    providers = {"mock": mock}
    assert await verify_payment(factory(db_engine), providers, new_payment) is Outcome.APPLY_PAID
    paid = await one(db_engine, ORDER_STATE, o=new.order_id)
    assert (paid.status, paid.lines) == ("in_progress", ["awaiting_delivery"])
    released = await one(db_engine, ORDER_STATE, o=old.order_id)
    await mock.simulate(old_payment, "paid")
    assert await verify_payment(factory(db_engine), providers, old_payment) is Outcome.LATE_CAPTURE
    _late(await one(db_engine, PAYMENT_STATE, p=old_payment), 1000)
    assert await one(db_engine, ORDER_STATE, o=new.order_id) == paid
    assert await one(db_engine, ORDER_STATE, o=old.order_id) == released
    await _alerted_once(db_engine, old_payment, admins)


async def test_capture_found_after_outage_on_released_order(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-e: the job never releases during the outage; the admin does, after the grace."""
    at = epoch(1914)
    admins = await admin(db_session)
    order, payment_id = await _due(db_session, mock, at)
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    counts = await _job_release(db_engine, {"mock": Down()}, at)
    assert (counts["released"], counts["deferred"]) == (0, 1)
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before
    await _admin_release(db_engine, db_session, order, at)
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    await mock.simulate(payment_id, "paid")  # the provider is back and says paid
    outcome = await verify_payment(
        factory(db_engine), {"mock": mock}, payment_id, source="manual_reconcile"
    )
    assert outcome is Outcome.LATE_CAPTURE
    _late(await one(db_engine, PAYMENT_STATE, p=payment_id), 1000)
    assert await one(db_engine, ORDER_STATE, o=order.order_id) == released
    await _alerted_once(db_engine, payment_id, admins)


@pytest.mark.parametrize(("released_first", "year"), [(False, 1915), (True, 1916)])
async def test_mismatch_via_verification_is_late_capture(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    released_first: bool,
    year: int,
) -> None:
    """R-f through verification, before and after the release: the amount is stored."""
    at = epoch(year)
    admins = await admin(db_session)
    order, payment_id = await _due(
        db_session, mock, at, state="expired" if released_first else None
    )
    if released_first:
        assert (await _job_release(db_engine, {"mock": mock}, at))["released"] == 1
    before = await one(db_engine, ORDER_STATE, o=order.order_id)
    await mock.simulate(payment_id, "paid", 900)
    outcome = await verify_payment(factory(db_engine), {"mock": mock}, payment_id)
    assert outcome is (Outcome.LATE_CAPTURE if released_first else Outcome.LATE_CAPTURE_AND_FAIL)
    _late(await one(db_engine, PAYMENT_STATE, p=payment_id), 900)
    after = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (after.status, after.lines, after.cancelled_at) == (
        before.status,
        before.lines,
        before.cancelled_at,
    )
    await _alerted_once(db_engine, payment_id, admins)


async def test_mismatch_via_confirm_is_422_and_writes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-f through manual confirm: refused before any lock; no late capture, no alert."""
    at = epoch(1917)
    await admin(db_session)
    order, payment_id = await _due(db_session, mock, at, reference=False)
    await _admin_release(db_engine, db_session, order, at)
    before = (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
    )
    admin_id = (await create_user(db_session, role=UserRole.ADMIN)).id
    with pytest.raises(ManualConfirmRefusedError):
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await confirm_payment_manually(
                session,
                NO_STATUS,
                payment_id,
                admin_id=admin_id,
                provider_reference=f"dash_{payment_id.hex}",
                amount_cents=900,
                currency="USD",
                reason="dashboard shows 9.00 USD",
            )
    assert (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
    ) == before
    async with db_engine.connect() as conn:
        raised = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE entity_id = :p"
                " AND action = 'payment.alert_raised'"
            ),
            {"p": payment_id},
        )
    assert raised == 0


async def test_the_alert_lands_with_the_capture_not_a_job_run_later(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """R-g is a business loss outside the platform; what the platform owns is the alert's
    latency. It is written in the capture's own transaction, so it is there at once."""
    at = epoch(1918)
    admins = await admin(db_session)
    _, payment_id = await _due(db_session, mock, at, state="expired")
    assert (await _job_release(db_engine, {"mock": mock}, at))["released"] == 1
    await mock.simulate(payment_id, "paid")
    assert await _event_verified(db_engine, db_session, mock, payment_id) is Outcome.LATE_CAPTURE
    async with db_engine.connect() as conn:
        gap = await conn.scalar(
            text(
                "SELECT a.created_at - p.late_captured_at FROM audit_logs a"
                " JOIN payments p ON p.id = a.entity_id WHERE a.entity_id = :p"
                " AND a.action = 'payment.alert_raised'"
            ),
            {"p": payment_id},
        )
    assert gap is not None and abs(gap) < timedelta(seconds=5), gap
    await _alerted_once(db_engine, payment_id, admins)
