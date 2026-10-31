"""Races on the `manual` provider (VS-050 plan C1-C3, ADR-049): the administrator's confirm
against the job's release at the deadline, one reference typed on two payments, and one
payment confirmed twice. Each pair provably overlaps at its first order lock."""

import asyncio
import contextvars
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.exceptions import PaymentReferenceMismatchError
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure import manual, release
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.providers.manual import ManualPaymentProvider
from app.payments.infrastructure.release import release_stale
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    YEARS_AHEAD,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_order,
)

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]
STAGGER = 0.15
HOLD_OPEN_SECONDS = 1.0
MANUAL_HOLD = timedelta(days=7)
MANUAL = {"manual": ManualPaymentProvider()}
_racer: contextvars.ContextVar[int] = contextvars.ContextVar("racer", default=0)
_synced: contextvars.ContextVar[bool] = contextvars.ContextVar("synced", default=False)


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 10, 1, tzinfo=UTC)


async def _as(racer: int, work: Any) -> Any:
    _racer.set(racer)
    return await work()


def _sync_first_lock(monkeypatch: pytest.MonkeyPatch, order_ids: set[uuid.UUID]) -> None:
    """Each racer's first order lock meets the other's; racer 2 then waits STAGGER, so
    racer 1 takes its locks first. Later locks pass straight through."""
    barrier = asyncio.Barrier(2)
    for module in (release, manual):
        real = module.lock_order_for_change

        async def synced(session: Any, locked_id: uuid.UUID, _real: Any = real) -> Any:
            if locked_id in order_ids and not _synced.get():
                _synced.set(True)
                await meet_or_fail(barrier)
                if _racer.get() == 2:
                    await asyncio.sleep(STAGGER)
            return await _real(session, locked_id)

        monkeypatch.setattr(module, "lock_order_for_change", synced)


async def _confirm(engine: AsyncEngine, payment_id: uuid.UUID, reference: str | None) -> Any:
    async with engine.connect() as conn:
        admin = await conn.scalar(text("SELECT id FROM users WHERE role = 'admin' LIMIT 1"))
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            return await confirm_payment_manually(
                session,
                MANUAL,
                payment_id,
                admin_id=admin,
                provider_reference=reference,
                amount_cents=1000,
                currency="USD",
                reason="customer paid by Whish, seen in the account",
            )
    except PaymentReferenceMismatchError as exc:
        return exc


@pytest.fixture(autouse=True)
async def an_admin(db_session: AsyncSession) -> None:
    await create_user(db_session, role=UserRole.ADMIN)


@pytest.mark.parametrize("first", ["release", "confirm"])
async def test_a_confirm_and_the_release_at_the_deadline_never_both_win(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    at = epoch(2030 if first == "release" else 2031)
    order = await seed_order(db_session, placed_at=at)
    payment = await seed_attempt(db_session, order, initiated_at=at, provider="manual")
    _sync_first_lock(monkeypatch, {order.order_id})

    async def released() -> dict[str, int]:
        return await release_stale(
            factory(db_engine), MANUAL, now=at + MANUAL_HOLD, start_after=keyset_start(at)
        )

    async def confirmed() -> Any:
        return await _confirm(db_engine, payment, None)

    order_of = (1, 2) if first == "release" else (2, 1)
    counts, outcome = await asyncio.gather(_as(order_of[0], released), _as(order_of[1], confirmed))
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    paid = await one(db_engine, PAYMENT_STATE, p=payment)
    if first == "release":
        assert (counts["released"], outcome) == (1, Outcome.LATE_CAPTURE)
        assert (state.status, paid.status) == ("cancelled", "expired")
        assert paid.late_captured_at is not None
    else:
        assert (outcome, counts["released"], counts["rechecked"]) == (Outcome.APPLY_PAID, 0, 1)
        assert (state.status, state.lines, paid.status) == (
            "in_progress",
            ["awaiting_delivery"],
            "paid",
        )


async def test_one_reference_typed_on_two_payments_pays_one(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the reference lock the loser trips `uq_payments_provider_reference` (a 500)."""
    at = epoch(2032)
    first, second = (
        await seed_order(db_session, placed_at=at),
        await seed_order(db_session, placed_at=at),
    )
    one_id = await seed_attempt(db_session, first, initiated_at=at, provider="manual")
    two_id = await seed_attempt(db_session, second, initiated_at=at, provider="manual")
    _sync_first_lock(monkeypatch, {first.order_id, second.order_id})
    real_find = SqlPaymentStore.find_by_reference

    async def find_then_hold(self: SqlPaymentStore, *args: Any) -> Any:
        found = await real_find(self, *args)
        if _racer.get() == 1:  # racer 2 looks while racer 1 has not committed yet
            await asyncio.sleep(HOLD_OPEN_SECONDS)
        return found

    monkeypatch.setattr(SqlPaymentStore, "find_by_reference", find_then_hold)
    reference = f"WH-{uuid.uuid4().hex[:10]}"
    results = await asyncio.gather(
        _as(1, lambda: _confirm(db_engine, one_id, reference)),
        _as(2, lambda: _confirm(db_engine, two_id, reference)),
    )
    assert results[0] is Outcome.APPLY_PAID
    assert isinstance(results[1], PaymentReferenceMismatchError)
    states = [(await one(db_engine, PAYMENT_STATE, p=p)).status for p in (one_id, two_id)]
    assert states == ["paid", "pending"]


async def test_one_payment_confirmed_twice_is_paid_once(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = epoch(2033)
    order = await seed_order(db_session, placed_at=at)
    payment = await seed_attempt(db_session, order, initiated_at=at, provider="manual")
    _sync_first_lock(monkeypatch, {order.order_id})
    outcomes = await asyncio.gather(
        _as(1, lambda: _confirm(db_engine, payment, None)),
        _as(2, lambda: _confirm(db_engine, payment, None)),
    )
    assert list(outcomes) == [Outcome.APPLY_PAID, Outcome.NOOP]
    async with db_engine.connect() as conn:
        verified = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE entity_id = :p"
                " AND action = 'payment.verified'"
            ),
            {"p": payment},
        )
    assert verified == 1
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).lines == ["awaiting_delivery"]
