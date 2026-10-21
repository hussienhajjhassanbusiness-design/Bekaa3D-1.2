"""VS-023b races (plan 3.6): every racer is made to wait on the `orders` row lock first, so
the transactions genuinely overlap; the locked winner decides, the loser re-reads under the lock."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import running_app
from tests.integration.fulfillment.delivery_support import (
    admin_client,
    effects,
    line_row,
    mark_sent,
    seed_stl_order,
    wait_for_lock_waiters,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]


@asynccontextmanager
async def order_lock(engine: AsyncEngine, order_id: uuid.UUID) -> AsyncIterator[AsyncConnection]:
    """Another writer (a refund, a payment) holding the order, as VS-030 will."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT id FROM orders WHERE id = :o FOR UPDATE"), {"o": order_id})
        try:
            yield conn
        finally:
            await conn.rollback()


async def _admins(app: FastAPI, db: AsyncSession, count: int) -> list[httpx.AsyncClient]:
    return [(await admin_client(app, db))[0] for _ in range(count)]


async def test_two_administrators_marking_one_line_sent_get_one_200_and_one_409(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session)
    async with running_app(make_app) as app:
        clients = await _admins(app, db_session, 2)
        try:
            async with order_lock(db_engine, order.order_id) as held:
                racers = [asyncio.create_task(mark_sent(c, order.order_id, line)) for c in clients]
                await wait_for_lock_waiters(db_engine, 2)
                await held.commit()
            first, second = await asyncio.gather(*racers)
        finally:
            for client in clients:
                await client.aclose()
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["code"] == "INVALID_STATE_TRANSITION"
    assert loser.json()["reason"] == "already_delivered"
    assert await effects(db_engine, line) == (1, 1, 1, 1)
    assert (await line_row(db_engine, line)).fulfillment_status == "delivered"


async def test_a_refund_that_commits_first_makes_the_delivery_a_409_that_writes_nothing(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session)
    async with running_app(make_app) as app:
        (client,) = await _admins(app, db_session, 1)
        try:
            async with order_lock(db_engine, order.order_id) as refund:
                racer = asyncio.create_task(mark_sent(client, order.order_id, line))
                await wait_for_lock_waiters(db_engine, 1)
                await refund.execute(
                    text("UPDATE order_items SET fulfillment_status = 'refunded' WHERE id = :i"),
                    {"i": line},
                )
                await refund.commit()
            response = await racer
        finally:
            await client.aclose()
    assert response.status_code == 409
    assert response.json()["reason"] == "line_closed"
    assert (await line_row(db_engine, line)).fulfillment_status == "refunded"
    assert await effects(db_engine, line) == (0, 0, 0, 0)


async def test_the_line_state_is_read_after_the_lock_not_before_it(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Payment verification lands while the delivery waits: it must see `awaiting_delivery`."""
    order, line = await seed_stl_order(db_session, line_status="pending")
    async with running_app(make_app) as app:
        (client,) = await _admins(app, db_session, 1)
        try:
            async with order_lock(db_engine, order.order_id) as payment:
                racer = asyncio.create_task(mark_sent(client, order.order_id, line))
                await wait_for_lock_waiters(db_engine, 1)
                await payment.execute(
                    text(
                        "UPDATE order_items SET fulfillment_status = 'awaiting_delivery'"
                        " WHERE id = :i"
                    ),
                    {"i": line},
                )
                await payment.commit()
            response = await racer
        finally:
            await client.aclose()
    assert response.status_code == 200, response.text
    assert await effects(db_engine, line) == (1, 1, 1, 1)


async def test_a_delivery_on_an_unpaid_line_is_never_recorded(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """No payment lands: the pending line stays pending and nothing is written."""
    order, line = await seed_stl_order(db_session, line_status="pending")
    async with running_app(make_app) as app:
        (client,) = await _admins(app, db_session, 1)
        try:
            response = await mark_sent(client, order.order_id, line)
        finally:
            await client.aclose()
    assert (response.status_code, response.json()["reason"]) == (409, "not_awaiting_delivery")
    assert (await line_row(db_engine, line)).fulfilled_at is None
    assert await effects(db_engine, line) == (0, 0, 0, 0)
