"""`reconcile_stuck` on Postgres (VS-024 plan 3.2, 6.2): missed callbacks applied, the
Tx2-crash attempt recovered, no transaction open during the query, the breaker, the run
deadline, and the once-only alerts. Each test runs from its own far-past epoch."""

import asyncio
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.infrastructure import verification
from app.payments.infrastructure.payments import stale_live_query
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.reconcile import reconcile_stuck
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    UNTOUCHED,
    YEARS_AHEAD,
    Down,
    SeededOrder,
    Spy,
    alerts,
    drop_alert_emails,  # noqa: F401
    explain,
    factory,
    forget_provider_alerts,
    keyset_start,
    one,
    provider_alerts,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import (
    OPEN_TRANSACTIONS,
    Hanging,
    NoStatus,
    _forget,
)
from tests.integration.payments.verification_support import Seeded, mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

LATER = timedelta(hours=2)  # past RECONCILE_MIN_AGE and STUCK_AFTER


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 9, 1, tzinfo=UTC)


async def _run(
    engine: AsyncEngine, providers: Any, start: datetime, now: datetime, **kw: Any
) -> dict[str, int]:
    return await reconcile_stuck(
        factory(engine), providers, now=now, start_after=keyset_start(start), **kw
    )


async def _live(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, **attempt: Any
) -> tuple[SeededOrder, uuid.UUID]:
    order = await seed_order(db, placed_at=at)
    return order, await seed_attempt(db, order, initiated_at=at, mock=mock, **attempt)


async def test_a_missed_callback_is_applied_in_one_run(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1950)
    order, payment_id = await _live(db_session, mock, at, state="paid")
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["seen"], counts["applied"]) == (1, 1), counts
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "paid"
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).lines == ["awaiting_delivery"]


async def test_the_checkout_crash_attempt_gets_its_reference_and_its_result(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1951)
    _, payment_id = await _live(db_session, mock, at, state="paid", reference=False)
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).provider_payment_id is None
    assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["applied"] == 1
    payment = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert payment.status == "paid" and payment.provider_payment_id.startswith("mock_")


@pytest.mark.parametrize(("state", "year"), [("failed", 1952), ("expired", 1953)])
async def test_failed_and_expired_mark_the_attempt_and_keep_the_order_payable(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    state: str,
    year: int,
) -> None:
    at = epoch(year)
    order, payment_id = await _live(db_session, mock, at, state=state)
    assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["applied"] == 1
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == state
    kept = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (kept.status, kept.cancelled_at, kept.lines) == ("pending_payment", None, ["pending"])


async def test_an_attempt_younger_than_the_minimum_age_is_not_asked(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1954)
    await _live(db_session, mock, at, state="paid")
    spy = Spy(mock)
    counts = await _run(db_engine, {"mock": spy}, at, at + timedelta(minutes=4))
    assert (spy.calls, counts["seen"]) == (0, 0)
    assert (await _run(db_engine, {"mock": spy}, at, at + timedelta(minutes=5)))["seen"] == 1
    assert spy.calls == 1


async def test_the_breaker_opens_after_three_failures_with_one_alert_an_hour(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1955)
    await forget_provider_alerts(db_engine)
    seeded = [await _live(db_session, mock, at + timedelta(seconds=i)) for i in range(5)]
    before = [await one(db_engine, UNTOUCHED, o=o.order_id) for o, _ in seeded]
    for run in range(2):
        down = Down()
        counts = await _run(db_engine, {"mock": down}, at, at + LATER)
        assert down.calls == 3, run
        assert (counts["deferred"], counts["breaker_open"], counts["applied"]) == (3, 2, 0)
    assert [await one(db_engine, UNTOUCHED, o=o.order_id) for o, _ in seeded] == before
    assert await provider_alerts(db_engine) == 1


async def test_a_hanging_query_is_cut_with_no_transaction_open(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verification, "PROVIDER_TIMEOUT_SECONDS", 0.5)
    at = epoch(1956)
    order, _ = await _live(db_session, mock, at)
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    hanging = Hanging()
    task = asyncio.create_task(_run(db_engine, {"mock": hanging}, at, at + LATER))
    await asyncio.wait_for(hanging.entered.wait(), 5)
    async with db_engine.connect() as conn:
        open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
    counts = await asyncio.wait_for(task, 5)
    assert open_during_call == 0
    assert (counts["seen"], counts["deferred"]) == (1, 1)
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before


async def test_a_no_status_payment_is_never_asked_and_alerted_once_over_three_runs(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1957)
    _, payment_id = await _live(db_session, mock, at, state="paid")
    stub = NoStatus()
    for _ in range(3):
        assert (await _run(db_engine, {"mock": stub}, at, at + LATER))["skipped_manual"] == 1
    assert stub.calls == []
    assert await alerts(db_engine, payment_id) == {"manual_confirmation_due": 1}
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "pending"


async def test_an_unconfigured_provider_is_skipped_with_its_alert(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1958)
    _, payment_id = await _live(db_session, mock, at, state="paid")
    assert (await _run(db_engine, {}, at, at + LATER))["skipped_unconfigured"] == 1
    assert await alerts(db_engine, payment_id) == {"provider_not_configured": 1}


async def test_the_deadline_truncates_the_run_and_the_next_run_continues(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1959)
    first = await _live(db_session, mock, at, state="paid")
    second = await _live(db_session, mock, at + timedelta(seconds=1), state="paid")
    ticks = itertools.chain([0.0, 0.0], itertools.repeat(1000.0))
    counts = await _run(
        db_engine, {"mock": mock}, at, at + LATER, clock=lambda: next(ticks), deadline_seconds=1
    )
    assert (counts["seen"], counts["applied"], counts["truncated"]) == (1, 1, 1), counts
    assert (await one(db_engine, PAYMENT_STATE, p=second[1])).status == "pending"
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["seen"], counts["applied"], counts["truncated"]) == (1, 1, 0), counts
    assert {(await one(db_engine, PAYMENT_STATE, p=p)).status for p in (first[1], second[1])} == {
        "paid"
    }


async def test_stuck_is_raised_once_a_day(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1960)
    _, payment_id = await _live(db_session, mock, at)
    for _ in range(2):
        assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["stuck"] == 1
    assert await alerts(db_engine, payment_id) == {"stuck": 1}
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE audit_logs SET created_at = created_at - interval '25 hours'"
                " WHERE entity_id = :p AND action = 'payment.alert_raised'"
            ),
            {"p": payment_id},
        )
    await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert await alerts(db_engine, payment_id) == {"stuck": 2}


async def test_unknown_writes_nothing_and_alerts_once(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1961)
    order, payment_id = await _live(db_session, mock, at)
    await _forget(Seeded(order.user_id, order.order_id, payment_id, "", ""))
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    for _ in range(2):
        assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["unknown"] == 1
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before
    assert await alerts(db_engine, payment_id) == {"reference_unknown": 1}


async def test_the_selection_uses_ix_payments_unsettled(db_engine: AsyncEngine) -> None:
    query = stale_live_query(before=epoch(1962), after=keyset_start(epoch(1962)), limit=50)
    natural = await explain(db_engine, query, seqscan=True)
    forced = await explain(db_engine, query, seqscan=False)
    print(f"\nEXPLAIN reconcile candidates (planner's choice):\n{natural}")
    print(f"EXPLAIN reconcile candidates (enable_seqscan = off):\n{forced}")
    assert "ix_payments_unsettled" in forced, forced
    assert "LockRows" not in natural + forced


async def test_one_run_over_a_seeded_set_counts_each_outcome(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1963)
    step = itertools.count(1)

    async def live(**attempt: Any) -> uuid.UUID:
        moment = at + timedelta(seconds=next(step))
        order = await seed_order(db_session, placed_at=moment)
        return await seed_attempt(db_session, order, initiated_at=moment, mock=mock, **attempt)

    await live(state="paid")
    await live(state="failed")
    await live(state="expired")
    mismatch = await live()
    await mock.simulate(mismatch, "paid", 900)
    await live()  # pending: stuck
    await live(state="processing")  # stuck
    gone = await live()
    gone_order = await db_session.scalar(
        text("SELECT order_id FROM payments WHERE id = :p"), {"p": gone}
    )
    await _forget(Seeded(uuid.uuid4(), gone_order, gone, "", ""))
    await live(status="failed", state="paid")  # not live: never selected
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    print("\nRECONCILE RUN COUNTERS:", counts)
    assert counts == {
        "seen": 7,
        "applied": 5,
        "unchanged": 1,
        "deferred": 0,
        "unknown": 1,
        "stuck": 2,
        "skipped_manual": 0,
        "skipped_unconfigured": 0,
        "breaker_open": 0,
        "truncated": 0,
    }


async def test_a_live_attempt_younger_than_an_hour_is_not_stuck(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1964)
    _, payment_id = await _live(db_session, mock, at)
    counts = await _run(db_engine, {"mock": mock}, at, at + timedelta(minutes=59))
    assert (counts["seen"], counts["stuck"]) == (1, 0), counts
    assert await alerts(db_engine, payment_id) == {}


async def test_the_breaker_counts_only_consecutive_failures(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Fail, answer, fail, fail, fail: the answer resets the count, so all five are asked."""
    at = epoch(1965)
    await forget_provider_alerts(db_engine)
    for i in range(5):
        await _live(db_session, mock, at + timedelta(seconds=i))

    class Flaky(Down):
        async def query_status(self, ref: Any) -> Any:
            self.calls += 1
            if self.calls == 2:
                return await mock.query_status(ref)
            raise ProviderUnavailableError("connection refused")

    flaky = Flaky()
    counts = await _run(db_engine, {"mock": flaky}, at, at + LATER)
    assert (flaky.calls, counts["deferred"], counts["breaker_open"]) == (5, 4, 0), counts
