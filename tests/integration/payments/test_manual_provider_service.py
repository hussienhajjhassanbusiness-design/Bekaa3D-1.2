"""The `manual` provider at the service level on Postgres (VS-050, ADR-049): confirm with
an optional reference, unique when given; the job's release at the manual hold's deadline;
a late payment after it; the administrator's release at any time; reconciliation skips it."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.exceptions import (
    ManualConfirmRefusedError,
    PaymentAlreadyPaidOtherReferenceError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import ConfirmRefusal
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.providers.manual import ManualPaymentProvider
from app.payments.infrastructure.reconcile import reconcile_stuck
from app.payments.infrastructure.release import release_order_by_admin, release_stale
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    YEARS_AHEAD,
    SeededOrder,
    alerts,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import NoStatus

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

MANUAL_HOLD = timedelta(days=7)  # the `manual_payment_hold_period` default
SECOND = timedelta(seconds=1)
MANUAL = {"manual": ManualPaymentProvider()}
REASON = "customer paid by Whish transfer, seen in the business account"
RELEASE_AUDIT = """
    SELECT after_data FROM audit_logs WHERE entity_id = :o AND action = 'order.checkout_released'
"""
LATE_REFUNDS = "SELECT kind, status, amount_cents FROM refunds WHERE payment_id = :p"


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 7, 1, tzinfo=UTC)


async def _manual(db: AsyncSession, at: datetime, **order: Any) -> tuple[SeededOrder, uuid.UUID]:
    seeded = await seed_order(db, placed_at=at, **order)
    payment = await seed_attempt(db, seeded, initiated_at=at, provider="manual", reference=False)
    return seeded, payment


async def _confirm(
    engine: AsyncEngine, payment_id: uuid.UUID, reference: str | None, **kw: Any
) -> Outcome:
    async with engine.connect() as conn:
        admin = await conn.scalar(
            text("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1")
        )
    async with async_sessionmaker(engine)() as session, session.begin():
        return await confirm_payment_manually(
            session,
            kw.pop("providers", MANUAL),
            payment_id,
            admin_id=admin,
            provider_reference=reference,
            amount_cents=kw.pop("amount_cents", 1000),
            currency="USD",
            reason=REASON,
        )


@pytest.fixture
async def an_admin(db_session: AsyncSession) -> uuid.UUID:
    return (await create_user(db_session, role=UserRole.ADMIN)).id


# --- Confirm: the reference is optional, and unique when given -------------------------------


@pytest.mark.usefixtures("an_admin")
async def test_confirm_without_a_reference_pays_and_moves_the_stl_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    first = await _manual(db_session, epoch(2001))
    second = await _manual(db_session, epoch(2001))
    for order, payment in (first, second):  # two omitted references never collide
        assert await _confirm(db_engine, payment, None) is Outcome.APPLY_PAID
        state = await one(db_engine, PAYMENT_STATE, p=payment)
        assert (state.status, state.provider_payment_id) == ("paid", None)
        paid = await one(db_engine, ORDER_STATE, o=order.order_id)
        assert (paid.status, paid.lines) == ("in_progress", ["awaiting_delivery"])


@pytest.mark.usefixtures("an_admin")
async def test_a_blank_reference_is_none_and_a_given_one_is_trimmed_case_kept(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    _, blank = await _manual(db_session, epoch(2002))
    _, given = await _manual(db_session, epoch(2002))
    _, same = await _manual(db_session, epoch(2002))
    _, other_case = await _manual(db_session, epoch(2002))
    reference = f"Wh-{uuid.uuid4().hex[:8]}"
    await _confirm(db_engine, blank, "   ")
    await _confirm(db_engine, given, f"  {reference} ")
    assert (await one(db_engine, PAYMENT_STATE, p=blank)).provider_payment_id is None
    assert (await one(db_engine, PAYMENT_STATE, p=given)).provider_payment_id == reference
    with pytest.raises(PaymentReferenceMismatchError):
        await _confirm(db_engine, same, reference)
    assert (await one(db_engine, PAYMENT_STATE, p=same)).status == "pending"
    await _confirm(db_engine, other_case, reference.upper())
    assert (await one(db_engine, PAYMENT_STATE, p=other_case)).status == "paid"


@pytest.mark.usefixtures("an_admin")
async def test_any_other_provider_still_needs_its_reference(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_order(db_session, placed_at=epoch(2003))
    payment = await seed_attempt(db_session, order, initiated_at=epoch(2003), reference=False)
    with pytest.raises(ManualConfirmRefusedError) as refused:
        await _confirm(db_engine, payment, None, providers={"mock": NoStatus()})
    assert refused.value.refusal is ConfirmRefusal.REFERENCE_REQUIRED
    assert (await one(db_engine, PAYMENT_STATE, p=payment)).status == "pending"


@pytest.mark.usefixtures("an_admin")
async def test_confirm_needs_no_configured_adapter_for_manual(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """`manual` is known by its name: a later `PAYMENT_PROVIDER` change cannot strand it."""
    _, payment = await _manual(db_session, epoch(2004))
    assert await _confirm(db_engine, payment, None, providers={}) is Outcome.APPLY_PAID


async def test_the_job_releases_a_manual_order_even_with_no_adapter_configured(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    at = epoch(2005)
    order, _ = await _manual(db_session, at)
    counts = await release_stale(
        factory(db_engine), {}, now=at + MANUAL_HOLD, start_after=keyset_start(at)
    )
    assert counts["released"] == 1, counts
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"


# --- The job: the manual hold, then the platform's own `expired` ------------------------------


async def test_the_job_releases_a_manual_order_exactly_at_its_own_deadline(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    at = epoch(2010)
    order, payment = await _manual(db_session, at)
    deadline = at + MANUAL_HOLD

    async def run(now: datetime) -> dict[str, int]:
        return await release_stale(
            factory(db_engine), MANUAL, now=now, start_after=keyset_start(at)
        )

    for early in (at + timedelta(hours=1), deadline - SECOND):  # past the 30 min online hold
        counts = await run(early)
        assert (counts["seen"], counts["not_due"], counts["released"]) == (1, 1, 0), counts
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"
    counts = await run(deadline)
    assert counts["released"] == 1, counts
    state = await one(db_engine, PAYMENT_STATE, p=payment)
    assert (state.status, state.late_captured_at) == ("expired", None)
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (released.status, released.lines) == ("cancelled", ["cancelled"])
    assert (released.released_audits, released.notices, released.emails) == (1, 1, 1)
    audit = (await one(db_engine, RELEASE_AUDIT, o=order.order_id)).after_data
    assert (audit["source"], audit["reason"]) == ("job", "manual_hold_expired")
    assert await alerts(db_engine, payment) == {}
    again = await seed_order(
        db_session, placed_at=at, user_id=order.user_id, stl_id=order.stl_id
    )  # the ownership index is free again
    assert (await one(db_engine, ORDER_STATE, o=again.order_id)).lines == ["pending"]


@pytest.mark.usefixtures("an_admin")
async def test_a_payment_after_the_release_is_a_late_capture_with_its_refund(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    at = epoch(2011)
    order, payment = await _manual(db_session, at)
    await release_stale(
        factory(db_engine), MANUAL, now=at + MANUAL_HOLD, start_after=keyset_start(at)
    )
    outcome = await _confirm(db_engine, payment, f"late-{uuid.uuid4().hex[:6]}")
    assert outcome is Outcome.LATE_CAPTURE
    state = await one(db_engine, PAYMENT_STATE, p=payment)
    assert state.status == "expired" and state.late_captured_at is not None
    assert (await one(db_engine, LATE_REFUNDS, p=payment)) == ("late_capture", "pending", 1000)
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"


@pytest.mark.usefixtures("an_admin")
async def test_a_late_captured_attempt_keeps_its_reference(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """VS-050 audit A-01: money already recorded late; a new reference is a second transfer."""
    at = epoch(2014)
    _, payment = await _manual(db_session, at)
    await release_stale(
        factory(db_engine), MANUAL, now=at + MANUAL_HOLD, start_after=keyset_start(at)
    )
    first = f"late-{uuid.uuid4().hex[:6]}"
    assert await _confirm(db_engine, payment, first) is Outcome.LATE_CAPTURE
    with pytest.raises(PaymentAlreadyPaidOtherReferenceError):
        await _confirm(db_engine, payment, f"other-{uuid.uuid4().hex[:6]}")
    assert await _confirm(db_engine, payment, first) is Outcome.NOOP
    assert await _confirm(db_engine, payment, None) is Outcome.NOOP
    assert (await one(db_engine, PAYMENT_STATE, p=payment)).provider_payment_id == first
    # `one()` fails on a second row: still the single obligation for the first transfer.
    assert (await one(db_engine, LATE_REFUNDS, p=payment)) == ("late_capture", "pending", 1000)


async def test_the_administrator_may_release_a_manual_order_at_once(
    db_engine: AsyncEngine, db_session: AsyncSession, an_admin: uuid.UUID
) -> None:
    """VS-050 Q3: no 24 h grace after a 7-day hold; the reason is still mandatory."""
    at = epoch(2012)
    order, payment = await _manual(db_session, at)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        released = await release_order_by_admin(
            session,
            order.order_id,
            admin_id=an_admin,
            reason="customer said by phone they will not pay",
            events_reviewed=False,
            now=at + timedelta(minutes=5),
        )
    assert released.attempts_expired == (payment,)
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"
    assert (await one(db_engine, PAYMENT_STATE, p=payment)).status == "expired"


async def test_reconciliation_never_asks_or_alerts_about_a_manual_attempt(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    at = epoch(2013)
    _, payment = await _manual(db_session, at)
    counts = await reconcile_stuck(
        factory(db_engine), MANUAL, now=at + timedelta(days=2), start_after=keyset_start(at)
    )
    assert counts["skipped_manual"] >= 1, counts
    assert await alerts(db_engine, payment) == {}
    assert (await one(db_engine, PAYMENT_STATE, p=payment)).status == "pending"
