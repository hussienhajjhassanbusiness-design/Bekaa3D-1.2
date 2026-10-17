"""VS-023 payment races on real Postgres (plan 6.3, 8.1). Racers meet at a barrier on the
first lock (`orders FOR UPDATE`); a stagger picks which one takes it first. The invariant:
one paid transition, one history row each, one STL line move, no deadlock."""

import asyncio
import contextvars
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.verify_payments import verify_payments
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure import ordering_side
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import apply_provider_result, verify_event
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from app.payments.public import fail_attempt, payment_store
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import async_client, running_app
from tests.integration.payments.support import NOW
from tests.integration.payments.test_verification import _event
from tests.integration.payments.verification_support import (
    WEBHOOK,
    Seeded,
    event_body,
    mock_fixture,  # noqa: F401
    paid_once,
    paid_state,
    pending_payment,
    signed,
)

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app"),
]
STAGGER = 0.15
_delay: contextvars.ContextVar[float] = contextvars.ContextVar("delay", default=0.0)


def _synced_locks(monkeypatch: pytest.MonkeyPatch, order_id: uuid.UUID, racers: int) -> None:
    """Both racers reach `orders FOR UPDATE` together; each then waits its own stagger."""
    barrier = asyncio.Barrier(racers)
    real = getattr(ordering_side, "lock_order_for_change")  # noqa: B009

    async def synced(session: Any, locked_id: uuid.UUID) -> Any:
        if locked_id == order_id:
            await meet_or_fail(barrier)
            await asyncio.sleep(_delay.get())
        return await real(session, locked_id)

    monkeypatch.setattr(ordering_side, "lock_order_for_change", synced)


async def _as(delay: float, work: Callable[[], Any]) -> Any:
    _delay.set(delay)
    return await work()


def _factory(engine: AsyncEngine) -> Any:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.parametrize("first", ["webhook", "job"])
async def test_webhook_verification_against_the_cron_job_pays_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)
    _synced_locks(monkeypatch, seeded.order_id, 2)
    factory, providers = _factory(db_engine), {"mock": mock}
    ctx = {"session_factory": factory, "payment_providers": providers}
    webhook_delay, job_delay = (0.0, STAGGER) if first == "webhook" else (STAGGER, 0.0)
    background, job = await asyncio.gather(
        _as(webhook_delay, lambda: verify_event(factory, providers, event_id)),
        _as(job_delay, lambda: verify_payments(ctx)),
    )
    assert background is (Outcome.APPLY_PAID if first == "webhook" else Outcome.NOOP)
    assert job["seen"] >= 1
    state = await paid_state(db_engine, seeded)
    assert paid_once(state), state


async def test_two_verifiers_of_one_event_pay_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)
    _synced_locks(monkeypatch, seeded.order_id, 2)
    factory, providers = _factory(db_engine), {"mock": mock}
    outcomes = await asyncio.gather(
        verify_event(factory, providers, event_id), verify_event(factory, providers, event_id)
    )
    assert sorted(o.value for o in outcomes if o is not None) == ["apply_paid", "noop"]
    assert paid_once(await paid_state(db_engine, seeded))


@pytest.mark.parametrize("first", ["paid", "expired"])
async def test_a_paid_answer_against_an_expiry_moves_the_attempt_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    seeded = await pending_payment(db_session, mock)
    _synced_locks(monkeypatch, seeded.order_id, 2)
    factory = _factory(db_engine)

    async def apply(result: ProviderResult) -> Outcome:
        async with factory() as session, session.begin():
            return await apply_provider_result(
                session, seeded.payment_id, result, source="reconcile", actor_user_id=None
            )

    paid_delay, expiry_delay = (0.0, STAGGER) if first == "paid" else (STAGGER, 0.0)
    paid, expired = await asyncio.gather(
        _as(paid_delay, lambda: apply(ProviderResult("paid", 1000, "USD"))),
        _as(expiry_delay, lambda: apply(ProviderResult("expired", None, None))),
    )
    state = await paid_state(db_engine, seeded)
    if first == "paid":
        assert (paid, expired) == (Outcome.APPLY_PAID, Outcome.NOOP)
        assert paid_once(state), state
    else:
        assert (expired, paid) == (Outcome.MARK_EXPIRED, Outcome.LATE_CAPTURE)
        assert (state.payment_status, state.late_captured, state.late_audits) == (
            "expired",
            True,
            1,
        )
        assert (state.line_status, state.line_transitions, state.order_transitions) == (
            "pending",
            0,
            0,
        )
        assert (state.verified_audits, state.outbox, state.notifications) == (0, 0, 0)


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI]) -> AsyncIterator[FastAPI]:
    async with running_app(make_app) as running:
        yield running


async def test_a_duplicate_webhook_delivered_in_parallel_is_stored_and_paid_once(
    app: FastAPI,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded: Seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    barrier = asyncio.Barrier(2)
    real = SqlWebhookEventStore.insert_if_new

    async def synced(self: SqlWebhookEventStore, event: Any) -> Any:
        await meet_or_fail(barrier)
        return await real(self, event)

    monkeypatch.setattr(SqlWebhookEventStore, "insert_if_new", synced)
    body = event_body(seeded)
    clients = [async_client(app), async_client(app)]
    try:
        responses: list[httpx.Response] = await asyncio.gather(
            *(c.post(WEBHOOK, content=body, headers=signed(body)) for c in clients)
        )
    finally:
        for c in clients:
            await c.aclose()
    assert [r.status_code for r in responses] == [200, 200]
    async with db_engine.connect() as conn:
        stored = await conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE payment_id = :p"),
            {"p": seeded.payment_id},
        )
    assert stored == 1
    assert paid_once(await paid_state(db_engine, seeded))


async def test_a_paid_answer_racing_a_cancellation_sees_the_cancelled_order(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """The orders lock alone decides this race. The cancel stands in for VS-024's
    `release_stale_checkouts` and locks as ADR-024 says: orders, then lines. Without the
    orders lock, apply reads the order before the cancel commits, and pays it."""
    seeded = await pending_payment(db_session, mock)
    held = asyncio.Event()

    async def cancel() -> None:
        async with db_engine.begin() as conn:
            await conn.execute(
                text("SELECT id FROM orders WHERE id = :o FOR UPDATE"), {"o": seeded.order_id}
            )
            await conn.execute(
                text("SELECT id FROM order_items WHERE order_id = :o ORDER BY id FOR UPDATE"),
                {"o": seeded.order_id},
            )
            held.set()
            await asyncio.sleep(STAGGER)  # apply is now waiting on one of these locks
            await conn.execute(
                text("UPDATE orders SET status = 'cancelled', cancelled_at = now() WHERE id = :o"),
                {"o": seeded.order_id},
            )

    async def apply() -> Outcome:
        await asyncio.wait_for(held.wait(), timeout=5)
        async with _factory(db_engine)() as session, session.begin():
            return await apply_provider_result(
                session,
                seeded.payment_id,
                ProviderResult("paid", 1000, "USD"),
                source="reconcile",
                actor_user_id=None,
            )

    outcome, _ = await asyncio.gather(apply(), cancel())
    state = await paid_state(db_engine, seeded)
    assert outcome is Outcome.LATE_CAPTURE_AND_FAIL
    assert (state.payment_status, state.late_captured, state.order_status) == (
        "failed",
        True,
        "cancelled",
    )
    assert (state.line_status, state.line_transitions, state.verified_audits) == ("pending", 0, 0)


async def test_a_paid_answer_racing_checkout_tx2_failing_the_attempt_sees_it_failed(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """The payments lock alone decides this race: checkout's Tx2 fails the attempt with
    an UPDATE of `payments` only (plan 8.1). Without the lock, apply would decide from
    the stale `pending` row and overwrite `failed` with `paid`."""
    seeded = await pending_payment(db_session, mock)
    held = asyncio.Event()

    async def tx2_fails_the_attempt() -> None:
        async with _factory(db_engine)() as session, session.begin():
            await fail_attempt(
                payment_store(session),
                SqlAuditWriter(session),
                payment_id=seeded.payment_id,
                order_id=seeded.order_id,
                actor_user_id=seeded.user_id,
                at=NOW,
            )
            held.set()
            await asyncio.sleep(STAGGER)  # apply now waits on the payment row

    async def apply() -> Outcome:
        await asyncio.wait_for(held.wait(), timeout=5)
        async with _factory(db_engine)() as session, session.begin():
            return await apply_provider_result(
                session,
                seeded.payment_id,
                ProviderResult("paid", 1000, "USD"),
                source="reconcile",
                actor_user_id=None,
            )

    outcome, _ = await asyncio.gather(apply(), tx2_fails_the_attempt())
    state = await paid_state(db_engine, seeded)
    assert outcome is Outcome.LATE_CAPTURE
    assert (state.payment_status, state.verified, state.late_captured) == ("failed", False, True)
    assert (state.line_status, state.line_transitions, state.verified_audits) == ("pending", 0, 0)
