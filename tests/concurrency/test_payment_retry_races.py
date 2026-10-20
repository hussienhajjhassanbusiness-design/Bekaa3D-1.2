"""VS-024 retry races on real Postgres (plan 6.3 #1, #4, #6), through the HTTP route.
Racers meet at a barrier on their first `orders FOR UPDATE`; a stagger picks who locks
first. The invariant: at most one live attempt, and never a cancelled order with one."""

import asyncio
import contextvars
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure import ordering_side, release
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_stale
from app.payments.infrastructure.verification import verify_event
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app"),
]
STAGGER = 0.15
HELD = 0.5  # the first locker keeps the orders lock past the stagger, so the other waits on it
ATTEMPTS = "SELECT status FROM payments WHERE order_id = :o ORDER BY initiated_at, id"
_racer: contextvars.ContextVar[int] = contextvars.ContextVar("racer", default=0)
_synced: contextvars.ContextVar[bool] = contextvars.ContextVar("synced", default=False)


async def _as(racer: int, work: Callable[[], Any]) -> Any:
    _racer.set(racer)
    return await work()


def _sync_first_order_lock(monkeypatch: pytest.MonkeyPatch, order_id: uuid.UUID) -> None:
    """Each racer's first lock of this order meets the other's; racer 2 then waits, and
    racer 1 holds the lock for HELD seconds before going on."""
    barrier = asyncio.Barrier(2)

    async def meet(locked_id: uuid.UUID) -> bool:
        if locked_id == order_id and not _synced.get():
            _synced.set(True)
            await meet_or_fail(barrier)
            if _racer.get() == 2:
                await asyncio.sleep(STAGGER)
            return _racer.get() == 1
        return False

    async def held(first: bool) -> None:
        if first:
            await asyncio.sleep(HELD)

    real_owned = SqlOrderStore.lock_owned_order

    async def owned(self: SqlOrderStore, locked_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        first = await meet(locked_id)
        locked = await real_owned(self, locked_id, user_id)
        await held(first)
        return locked

    monkeypatch.setattr(SqlOrderStore, "lock_owned_order", owned)
    for module in (ordering_side, release):
        real = module.lock_order_for_change

        async def synced(session: Any, locked_id: uuid.UUID, _real: Any = real) -> Any:
            first = await meet(locked_id)
            locked = await _real(session, locked_id)
            await held(first)
            return locked

        monkeypatch.setattr(module, "lock_order_for_change", synced)


async def _statuses(engine: AsyncEngine, order_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(ATTEMPTS), {"o": order_id})).scalars())


async def _signed_in(app: FastAPI, db: AsyncSession) -> tuple[httpx.AsyncClient, uuid.UUID]:
    user = await create_user(db)
    client = async_client(app)
    await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    return client, user.id


def _retry(client: httpx.AsyncClient, order_id: uuid.UUID) -> Callable[[], Any]:
    async def post() -> httpx.Response:
        return await client.post(
            f"/api/v1/me/orders/{order_id}/payments",
            json={},
            headers={
                "X-CSRF-Token": client.cookies["csrf_token"],
                "Idempotency-Key": f"race-{uuid.uuid4().hex}",
            },
        )

    return post


async def test_retry_against_retry_opens_one_attempt(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running_app(make_app) as app:
        client, user_id = await _signed_in(app, db_session)
        placed = datetime.now(UTC) - timedelta(minutes=5)
        order = await seed_order(db_session, placed_at=placed, user_id=user_id)
        await seed_attempt(db_session, order, initiated_at=placed, status="failed")
        _sync_first_order_lock(monkeypatch, order.order_id)
        try:
            first, second = await asyncio.gather(
                _as(1, _retry(client, order.order_id)), _as(2, _retry(client, order.order_id))
            )
        finally:
            await client.aclose()
    print(f"\nRETRY vs RETRY: {first.status_code} / {second.status_code} {second.text[:80]}")
    assert (first.status_code, second.status_code) == (201, 409)
    assert second.json()["code"] == "PAYMENT_ALREADY_ACTIVE"
    assert await _statuses(db_engine, order.order_id) == ["failed", "pending"]


@pytest.mark.parametrize("first", ["retry", "webhook"])
async def test_retry_against_the_webhook_failing_the_live_attempt(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    async with running_app(make_app) as app:
        client, user_id = await _signed_in(app, db_session)
        placed = datetime.now(UTC) - timedelta(minutes=5)
        order = await seed_order(db_session, placed_at=placed, user_id=user_id)
        live = await seed_attempt(db_session, order, initiated_at=placed, mock=mock, state="failed")
        event_id = await seed_event(db_session, live, received_at=datetime.now(UTC))
        _sync_first_order_lock(monkeypatch, order.order_id)

        async def webhook() -> Outcome | None:
            return await verify_event(factory(db_engine), {"mock": mock}, event_id)

        roles = (1, 2) if first == "retry" else (2, 1)
        try:
            response, outcome = await asyncio.gather(
                _as(roles[0], _retry(client, order.order_id)), _as(roles[1], webhook)
            )
        finally:
            await client.aclose()
    statuses = await _statuses(db_engine, order.order_id)
    print(f"\nRETRY vs WEBHOOK first={first}: {response.status_code} {outcome} {statuses}")
    assert outcome is Outcome.MARK_FAILED
    if first == "retry":
        assert (response.status_code, response.json()["code"]) == (409, "PAYMENT_ALREADY_ACTIVE")
        assert statuses == ["failed"]
    else:
        assert response.status_code == 201, response.text
        assert statuses == ["failed", "pending"]
    assert statuses.count("pending") + statuses.count("processing") <= 1


@pytest.mark.parametrize("first", ["release", "retry"])
async def test_retry_against_the_release_job(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    """The order is still inside its hold for the customer, while the job runs with a
    clock past the deadline of its only (failed, provider-expired) attempt."""
    async with running_app(make_app) as app:
        client, user_id = await _signed_in(app, db_session)
        placed = datetime.now(UTC) - HOLD + timedelta(minutes=2)
        order = await seed_order(db_session, placed_at=placed, user_id=user_id)
        await seed_attempt(
            db_session, order, initiated_at=placed, mock=mock, status="failed", state="expired"
        )
        _sync_first_order_lock(monkeypatch, order.order_id)

        async def released() -> dict[str, int]:
            return await release_stale(
                factory(db_engine),
                {"mock": mock},
                now=placed + HOLD + timedelta(minutes=1),
                start_after=keyset_start(placed),
            )

        roles = (1, 2) if first == "release" else (2, 1)
        try:
            counts, response = await asyncio.gather(
                _as(roles[0], released), _as(roles[1], _retry(client, order.order_id))
            )
        finally:
            await client.aclose()
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    statuses = await _statuses(db_engine, order.order_id)
    print(f"\nRETRY vs RELEASE first={first}: {response.status_code} {counts} {state.status}")
    if first == "release":
        assert counts["released"] == 1
        assert (response.status_code, response.json()["reason"]) == (409, "order_cancelled")
        assert (state.status, statuses) == ("cancelled", ["failed"])
    else:
        assert response.status_code == 201, response.text
        assert (counts["released"], counts["rechecked"]) == (0, 1)
        assert (state.status, statuses) == ("pending_payment", ["failed", "pending"])
    assert not (state.status == "cancelled" and "pending" in statuses)
