"""VS-031 races on real Postgres, through the real routes on one running app. Each racer is
made to wait on a held lock first, so the transactions overlap; the order they queue in
decides the winner, and the loser re-reads under the lock (ADR-024 d9)."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.core.security import hash_phone
from app.ordering.api import cancel as cancel_api
from app.ordering.infrastructure.cash import SqlCashChecks
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.fulfillment.cancel_support import blocks_of, customer_cancel_path
from tests.integration.fulfillment.delivery_support import admin_client, wait_for_lock_waiters
from tests.integration.fulfillment.order_support import (
    ORDERS,
    PhysicalOrder,
    handover_path,
    seed_physical_order,
    states,
    transition_path,
)
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    ITEMS,
    new_key,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    random_phone,
    setting,
)
from tests.integration.payments.refund_support import REFUNDS, statuses

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
RACE_TIMEOUT_SECONDS = 20
ITERATIONS = 100
DEADLOCK = "40P01"
Racer = Callable[[], Coroutine[Any, Any, httpx.Response]]


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI], db_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    async with (
        setting(db_engine, "pickup_address", "Workshop, Zahle"),
        running_app(make_app) as running,
    ):
        yield running


@asynccontextmanager
async def _held(engine: AsyncEngine, sql: str, **params: Any) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        await conn.execute(text(sql), params)
        try:
            yield conn
        finally:
            await conn.rollback()


async def _queued(engine: AsyncEngine, order_id: uuid.UUID, *racers: Racer) -> list[Any]:
    """Each racer starts once the one before it waits on the held `orders` lock; Postgres
    then grants the lock in that queue order."""
    lock = "SELECT id FROM orders WHERE id = :o FOR UPDATE"
    async with _held(engine, lock, o=order_id) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            await wait_for_lock_waiters(engine, n)
        await held.commit()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)


def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> Racer:
    async def call() -> httpx.Response:
        return await client.post(path, json=body, headers=_headers(client))

    return call


def _move(
    client: httpx.AsyncClient, order: PhysicalOrder, target: str, line: int, **extra: Any
) -> Racer:
    path = transition_path(order.order_id, order.line_ids[line])
    return _post(client, path, {"target_status": target} | extra)


async def _customer(app: FastAPI, db: AsyncSession) -> tuple[httpx.AsyncClient, uuid.UUID]:
    user = await create_user(db)
    client = async_client(app)
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return client, user.id


def _no_deadlock(*responses: httpx.Response) -> None:
    for response in responses:
        assert response.status_code != 500, response.text
        assert DEADLOCK not in response.text


# --- Done when 2: cancel versus start printing ----------------------------------------------


@pytest.mark.parametrize("lines", [1, 2], ids=["one_line", "printing_on_the_last_line"])
async def test_a_customer_cancel_racing_start_printing_has_exactly_one_winner(
    lines: int,
    app: FastAPI,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated, alternating who queues first. On two lines, printing starts on the line
    the cancel checks last (the highest id)."""
    monkeypatch.setattr(cancel_api, "CANCEL_RATE_LIMIT", 10 * ITERATIONS)
    admin, _ = await admin_client(app, db_session)
    customer, user_id = await _customer(app, db_session)
    try:
        for i in range(ITERATIONS):
            order = await seed_physical_order(
                db_session,
                payment_method="online",
                payment_status="paid",
                line_states=["pending"] * lines,
                user_id=user_id,
            )
            cancel = _post(customer, customer_cancel_path(order.order_id), {})
            printing = _move(admin, order, "in_production", line=lines - 1)
            racers = (cancel, printing) if i % 2 == 0 else (printing, cancel)
            first, second = await _queued(db_engine, order.order_id, *racers)
            _no_deadlock(first, second)
            assert (first.status_code, second.status_code) == (200, 409), second.text
            cancel_won = i % 2 == 0
            loser = "ORDER_NOT_CANCELLABLE" if not cancel_won else "INVALID_STATE_TRANSITION"
            assert second.json()["code"] == loser
            status, found = await states(db_engine, order.order_id)
            if cancel_won:
                assert (status, found) == ("cancelled", ["cancelled"] * lines)
            else:
                assert sorted(found) == sorted(["in_production"] + ["pending"] * (lines - 1))
                assert await _refunds(db_engine, order.order_id) == 0
    finally:
        await admin.aclose()
        await customer.aclose()


async def _refunds(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT count(*) FROM refunds WHERE order_id = :o"), {"o": order_id}
        )
    return int(found or 0)


# --- the handover and the cancels -----------------------------------------------------------


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_a_handover_racing_a_cancel_of_another_line_serialises_without_deadlock(
    cancel_first: bool, app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped", "ready_to_ship"])
    admins = [(await admin_client(app, db_session))[0] for _ in range(2)]
    try:
        cancel = _move(
            admins[0], order, "cancelled", line=1, cancel_reason="refused"
        )  # the ready one
        handover = _post(
            admins[1], handover_path(order.order_id), {"amount_cents": 1000, "currency": "USD"}
        )
        racers = (cancel, handover) if cancel_first else (handover, cancel)
        responses = await _queued(db_engine, order.order_id, *racers)
    finally:
        for client in admins:
            await client.aclose()
    _no_deadlock(*responses)
    cancelled, handed = (responses[0], responses[1]) if cancel_first else responses[::-1]
    assert cancelled.status_code == 200, cancelled.text
    status, lines = await states(db_engine, order.order_id)
    if cancel_first:
        assert handed.status_code == 200, handed.text
        assert (status, sorted(lines)) == ("completed", ["cancelled", "delivered"])
    else:
        assert handed.status_code == 409 and handed.json()["reason"] == "lines_not_ready"
        assert (status, sorted(lines)) == ("in_progress", ["cancelled", "shipped"])
    assert await blocks_of(db_engine, order.order_id) == []


@pytest.mark.parametrize("reason", ["other", "refused"])
async def test_two_cancels_of_the_last_two_lines_leave_one_status_and_at_most_one_block(
    reason: str, app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["ready_to_ship"] * 2)
    admins = [(await admin_client(app, db_session))[0] for _ in range(2)]
    try:
        responses = await _queued(
            db_engine,
            order.order_id,
            *(
                _move(c, order, "cancelled", line=n, cancel_reason=reason)
                for n, c in enumerate(admins)
            ),
        )
        due = await admins[0].get(ORDERS, params={"payment_due": "true", "limit": 100})
    finally:
        for client in admins:
            await client.aclose()
    _no_deadlock(*responses)
    assert [r.status_code for r in responses] == [200, 200]
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled", "cancelled"])
    assert str(order.order_id) not in [item["id"] for item in due.json()["items"]]
    assert len(await blocks_of(db_engine, order.order_id)) == (1 if reason == "refused" else 0)
    async with async_sessionmaker(db_engine)() as session:
        open_count = await SqlCashChecks(session).open_order_count(
            order.user_id, hash_phone(order.phone), at=datetime.now(UTC)
        )
    assert open_count == 0


@pytest.mark.parametrize("refund_first", [True, False])
async def test_an_stl_refund_racing_the_physical_lines_cancellation_both_commit(
    refund_first: bool, app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["in_production"],
        stl_line="delivered",
    )
    async with db_engine.connect() as conn:
        stl = await conn.scalar(
            text("SELECT id FROM order_items WHERE order_id = :o AND product_type = 'stl'"),
            {"o": order.order_id},
        )
    admins = [(await admin_client(app, db_session))[0] for _ in range(2)]
    try:
        cancel = _move(admins[0], order, "cancelled", line=0)

        async def refund() -> httpx.Response:
            return await admins[1].post(
                f"/api/v1/admin/orders/{order.order_id}/refunds",
                json={"items": [{"order_item_id": str(stl), "amount_cents": 500}], "reason": "x"},
                headers=_headers(admins[1]) | {"Idempotency-Key": new_key()},
            )

        racers = (refund, cancel) if refund_first else (cancel, refund)
        responses = await _queued(db_engine, order.order_id, *racers)
        queue = await admins[0].get(REFUNDS, params={"order_id": str(order.order_id)})
    finally:
        for client in admins:
            await client.aclose()
    _no_deadlock(*responses)
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
    assert sorted(item["kind"] for item in queue.json()["items"]) == ["admin", "cancellation"]


# --- BR-144: a checkout racing a cancel that blocks ------------------------------------------


@pytest.mark.usefixtures("shop_open")
@pytest.mark.parametrize("cancel_first", [True, False])
async def test_a_checkout_on_another_phone_racing_a_blocking_cancel_never_slips_past_it(
    cancel_first: bool, app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Both wait on the customer's cart lock, held here; the cancel already holds the
    order's. The checkout either commits first or sees the block (ADR-024 d9)."""
    lamp = await physical(db_session)
    customer, user_id = await _customer(app, db_session)
    admin, _ = await admin_client(app, db_session)
    order = await seed_physical_order(
        db_session, user_id=user_id, fulfillment="pickup", line_states=["ready_for_pickup"]
    )
    added = await customer.post(ITEMS, json={"product_id": str(lamp)}, headers=_headers(customer))
    assert added.status_code == 200, added.text

    async def checkout() -> httpx.Response:
        return await customer.post(
            CHECKOUT,
            json=pickup_body(random_phone()),
            headers=_headers(customer) | {"Idempotency-Key": new_key()},
        )

    cancel = _move(admin, order, "cancelled", line=0, cancel_reason="refused")
    lock = "SELECT id FROM carts WHERE user_id = :u FOR UPDATE"
    try:
        async with setting(db_engine, "cash_max_open_orders", 2):
            async with _held(db_engine, lock, u=user_id) as held:
                tasks = []
                for n, racer in enumerate(
                    (cancel, checkout) if cancel_first else (checkout, cancel)
                ):
                    tasks.append(asyncio.create_task(racer()))
                    await _cart_waiters(db_engine, n + 1)
                await held.commit()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)
    finally:
        await customer.aclose()
        await admin.aclose()
    _no_deadlock(*responses)
    cancelled, placed = responses if cancel_first else responses[::-1]
    assert cancelled.status_code == 200, cancelled.text
    assert len(await blocks_of(db_engine, order.order_id)) == 1
    if cancel_first:
        assert placed.status_code == 422 and placed.json()["code"] == "CASH_NOT_AVAILABLE"
    else:
        assert placed.status_code == 201, placed.text


async def _cart_waiters(engine: AsyncEngine, count: int, seconds: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database() AND query ILIKE '%FROM carts%FOR UPDATE%'"
                )
            )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"fewer than {count} requests ever waited on the cart lock")


# --- FR-08: one paid line, two cancels ------------------------------------------------------


@pytest.mark.parametrize("second", ["transition", "order_cancel", "customer"])
async def test_two_cancels_of_one_paid_line_refund_it_exactly_once(
    second: str, app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The loser re-reads the line under the orders lock: one 200, one 409, one refund."""
    admin, _ = await admin_client(app, db_session)
    other, _ = await admin_client(app, db_session)
    customer, user_id = await _customer(app, db_session)
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", user_id=user_id
    )
    racers = {
        "transition": _move(other, order, "cancelled", line=0),
        "order_cancel": _post(other, f"{ORDERS}/{order.order_id}/cancel", {"reason": "x"}),
        "customer": _post(customer, customer_cancel_path(order.order_id), {}),
    }
    try:
        first, loser = await _queued(
            db_engine, order.order_id, _move(admin, order, "cancelled", line=0), racers[second]
        )
    finally:
        for client in (admin, other, customer):
            await client.aclose()
    _no_deadlock(first, loser)
    assert (first.status_code, loser.status_code) == (200, 409), loser.text
    assert await _refunds(db_engine, order.order_id) == 1
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
