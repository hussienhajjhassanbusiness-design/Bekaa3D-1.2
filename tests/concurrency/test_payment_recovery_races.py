"""VS-024 recovery races on real Postgres (plan 6.3). Racers meet at a barrier, then a
stagger picks who goes first. Two job runs raise one alert per admin (the advisory lock);
overlapping releases release once; a release and a paid answer never both win."""

import asyncio
import contextlib
import contextvars
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.payments.domain.alerts import AlertKind
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure import ordering_side, release
from app.payments.infrastructure.alerts import SqlPaymentAlerts
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.reconcile import reconcile_stuck
from app.payments.infrastructure.release import release_stale
from app.payments.infrastructure.verification import apply_provider_result
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    YEARS_AHEAD,
    admin,
    alerts,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]
STAGGER = 0.15
HOLD_OPEN_SECONDS = 1.0
_racer: contextvars.ContextVar[int] = contextvars.ContextVar("racer", default=0)
_synced: contextvars.ContextVar[bool] = contextvars.ContextVar("synced", default=False)
PER_ADMIN = """
    SELECT count(*) FROM notifications WHERE user_id = :u
      AND payload->>'event' = 'payment.alert.stuck' AND payload->>'payment_id' = :p
"""


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 7, 1, tzinfo=UTC)


async def _as(racer: int, work: Any) -> Any:
    _racer.set(racer)
    return await work()


async def test_two_job_runs_raise_one_stuck_alert_per_admin(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Racer 1 holds its alert transaction open until racer 2 has run its check (or 1 s
    passes). With the advisory lock racer 2 waits and then sees racer 1's row."""
    at = epoch(1880)
    admins = await admin(db_session)
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, mock=mock)
    barrier, checked = asyncio.Barrier(2), asyncio.Event()
    real_raise, real_raised = SqlPaymentAlerts.raise_alert, SqlPaymentAlerts._raised

    async def raise_alert(self: SqlPaymentAlerts, kind: AlertKind, **kw: Any) -> bool:
        if kind is not AlertKind.STUCK or kw["payment_id"] != payment_id:
            return await real_raise(self, kind, **kw)
        await meet_or_fail(barrier)
        if _racer.get() == 2:
            await asyncio.sleep(STAGGER)
        raised = await real_raise(self, kind, **kw)
        if _racer.get() == 1:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(checked.wait(), HOLD_OPEN_SECONDS)
        return raised

    async def _raised(self: SqlPaymentAlerts, kind: AlertKind, pid: Any, *args: Any) -> bool:
        seen = await real_raised(self, kind, pid, *args)
        if kind is AlertKind.STUCK and pid == payment_id and _racer.get() == 2:
            checked.set()
        return seen

    monkeypatch.setattr(SqlPaymentAlerts, "raise_alert", raise_alert)
    monkeypatch.setattr(SqlPaymentAlerts, "_raised", _raised)

    async def run() -> dict[str, int]:
        return await reconcile_stuck(
            factory(db_engine),
            {"mock": mock},
            now=at + timedelta(hours=2),
            start_after=keyset_start(at),
        )

    first, second = await asyncio.gather(_as(1, run), _as(2, run))
    print(f"\nALERT RACE: runs={first['stuck']},{second['stuck']} checked={checked.is_set()}")
    assert first["stuck"] == second["stuck"] == 1
    assert await alerts(db_engine, payment_id) == {"stuck": 1}
    for admin_id, _ in admins:
        assert await one(db_engine, PER_ADMIN, u=admin_id, p=str(payment_id)) == (1,)


def _sync_first_lock(monkeypatch: pytest.MonkeyPatch, order_id: uuid.UUID, racers: int) -> None:
    """Each racer's first `orders FOR UPDATE` on this order meets the others, then the
    second racer waits STAGGER; later locks (apply's, on held rows) pass straight through."""
    barrier = asyncio.Barrier(racers)
    for module in (release, ordering_side):
        real = module.lock_order_for_change

        async def synced(session: Any, locked_id: uuid.UUID, _real: Any = real) -> Any:
            if locked_id == order_id and not _synced.get():
                _synced.set(True)
                await meet_or_fail(barrier)
                if _racer.get() == 2:
                    await asyncio.sleep(STAGGER)
            return await _real(session, locked_id)

        monkeypatch.setattr(module, "lock_order_for_change", synced)


async def test_two_overlapping_release_runs_release_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = epoch(1881)
    order = await seed_order(db_session, placed_at=at)
    await seed_attempt(db_session, order, initiated_at=at, mock=mock, state="expired")
    _sync_first_lock(monkeypatch, order.order_id, 2)

    async def run() -> dict[str, int]:
        return await release_stale(
            factory(db_engine),
            {"mock": mock},
            now=at + timedelta(hours=1),
            start_after=keyset_start(at),
        )

    first, second = await asyncio.gather(_as(1, run), _as(2, run))
    print(f"\nRELEASE RACE: {first} / {second}")
    assert (first["released"], second["released"]) == (1, 0)
    assert second["rechecked"] == 1
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.history, state.released_audits, state.notices) == (
        "cancelled",
        2,
        1,
        1,
    )


@pytest.mark.parametrize("first", ["release", "paid"])
async def test_a_release_and_a_paid_answer_never_both_win(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    at = epoch(1882 if first == "release" else 1883)
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, mock=mock, state="expired")
    _sync_first_lock(monkeypatch, order.order_id, 2)

    async def released() -> dict[str, int]:
        return await release_stale(
            factory(db_engine),
            {"mock": mock},
            now=at + timedelta(hours=1),
            start_after=keyset_start(at),
        )

    async def paid() -> Outcome:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            return await apply_provider_result(
                session,
                payment_id,
                ProviderResult("paid", 1000, "USD"),
                source="webhook",
                actor_user_id=None,
            )

    order_of = (1, 2) if first == "release" else (2, 1)
    counts, outcome = await asyncio.gather(_as(order_of[0], released), _as(order_of[1], paid))
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    payment = await one(db_engine, PAYMENT_STATE, p=payment_id)
    print(f"\nRELEASE vs PAID first={first}: {counts} {outcome} {state.status} {payment.status}")
    if first == "release":
        assert (counts["released"], outcome) == (1, Outcome.LATE_CAPTURE)
        assert (state.status, payment.status) == ("cancelled", "expired")
        assert payment.late_captured_at is not None
    else:
        assert (outcome, counts["released"], counts["rechecked"]) == (Outcome.APPLY_PAID, 0, 1)
        assert (state.status, state.lines, payment.status) == (
            "in_progress",
            ["awaiting_delivery"],
            "paid",
        )
    async with db_engine.connect() as conn:
        both = await conn.scalar(
            text(
                "SELECT count(*) FROM orders o JOIN payments p ON p.order_id = o.id"
                " WHERE o.id = :o AND o.cancelled_at IS NOT NULL AND p.status = 'paid'"
            ),
            {"o": order.order_id},
        )
    assert both == 0
