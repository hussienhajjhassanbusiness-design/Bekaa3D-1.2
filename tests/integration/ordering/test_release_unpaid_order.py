"""VS-024 step 9 on Postgres: `release_unpaid_order` (plan 3.6) and the `SqlOrderStore`
additions (3.4): the release candidates page, the owned-order lock, `set_cancelled`."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.ordering.infrastructure.orders import SqlOrderStore
from app.ordering.public import (
    OrderNotReleasableError,
    lock_order_for_change,
    release_candidates,
    release_unpaid_order,
)
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.recovery_support import ORDER_STATE, one, seed_order

pytestmark = pytest.mark.integration

EPOCH = datetime(1971, 4, 1, tzinfo=UTC)
AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
HISTORY = """
    SELECT order_item_id IS NULL AS order_row, from_status, to_status, actor_user_id, reason
    FROM order_status_history WHERE order_id = :o ORDER BY order_item_id NULLS LAST
"""


async def _release(engine: AsyncEngine, order_id: uuid.UUID, **kw: object) -> tuple[uuid.UUID, ...]:
    async with async_sessionmaker(engine)() as session, session.begin():
        locked = await lock_order_for_change(session, order_id)
        assert locked is not None
        return await release_unpaid_order(session, locked, at=AT, **kw)  # type: ignore[arg-type]


async def test_a_release_cancels_the_order_and_its_pending_lines_with_history(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_order(db_session, placed_at=EPOCH, physical=True)
    lines = await _release(db_engine, order.order_id, reason="hold_expired")
    assert len(lines) == 2
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.cancelled_at) == ("cancelled", AT)
    assert (state.lines, state.lines_stamped) == (["cancelled", "cancelled"], True)
    async with db_engine.connect() as conn:
        history = (await conn.execute(text(HISTORY), {"o": order.order_id})).all()
        stamps: Any = (
            await conn.execute(
                text("SELECT cancelled_at FROM order_items WHERE order_id = :o"),
                {"o": order.order_id},
            )
        ).scalars()
        assert set(stamps) == {AT}
    assert [tuple(row) for row in history] == [
        (False, "pending", "cancelled", None, "hold_expired"),
        (False, "pending", "cancelled", None, "hold_expired"),
        (True, "pending_payment", "cancelled", None, "hold_expired"),
    ]


async def test_an_admin_release_records_the_admin_on_every_history_row(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    order = await seed_order(db_session, placed_at=EPOCH)
    await _release(db_engine, order.order_id, reason="released_by_admin", actor_user_id=admin.id)
    async with db_engine.connect() as conn:
        rows = (await conn.execute(text(HISTORY), {"o": order.order_id})).all()
    assert {(row.actor_user_id, row.reason) for row in rows} == {(admin.id, "released_by_admin")}


async def test_a_release_frees_the_stl_for_the_same_customer(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_order(db_session, placed_at=EPOCH)
    with pytest.raises(IntegrityError, match="uq_order_items_stl_ownership"):
        await seed_order(db_session, placed_at=EPOCH, user_id=order.user_id, stl_id=order.stl_id)
    await db_session.rollback()
    await _release(db_engine, order.order_id, reason="hold_expired")
    again = await seed_order(
        db_session, placed_at=EPOCH, user_id=order.user_id, stl_id=order.stl_id
    )
    assert (await one(db_engine, ORDER_STATE, o=again.order_id)).lines == ["pending"]


@pytest.mark.parametrize(
    ("over", "line"),
    [
        ({"status": "in_progress"}, "awaiting_delivery"),
        ({"status": "cancelled", "cancelled_at": EPOCH}, "cancelled"),
    ],
    ids=["paid", "already-released"],
)
async def test_only_an_unpaid_uncancelled_online_order_is_released(
    db_engine: AsyncEngine, db_session: AsyncSession, over: dict[str, Any], line: str
) -> None:
    order = await seed_order(db_session, placed_at=EPOCH, **over)
    await db_session.execute(
        text(
            "UPDATE order_items SET fulfillment_status = CAST(:s AS order_item_status)"
            " WHERE order_id = :o"
        ),
        {"s": line, "o": order.order_id},
    )
    await db_session.commit()
    before = await one(db_engine, ORDER_STATE, o=order.order_id)
    with pytest.raises(OrderNotReleasableError):
        await _release(db_engine, order.order_id, reason="hold_expired")
    assert await one(db_engine, ORDER_STATE, o=order.order_id) == before


async def test_release_candidates_page_unpaid_online_orders_by_placement(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    epoch = datetime(1972, 4, 1, tzinfo=UTC)
    due = [
        (await seed_order(db_session, placed_at=epoch + timedelta(minutes=m))).order_id
        for m in range(5)
    ]
    paid = await seed_order(db_session, placed_at=epoch, status="in_progress")
    await db_session.execute(
        text("UPDATE order_items SET fulfillment_status = 'awaiting_delivery' WHERE order_id = :o"),
        {"o": paid.order_id},
    )
    await db_session.commit()
    await seed_order(db_session, placed_at=epoch, status="cancelled", cancelled_at=epoch)
    await seed_order(db_session, placed_at=epoch + timedelta(days=1))  # not yet placed_before
    start = (epoch - timedelta(microseconds=1), uuid.UUID(int=0))
    before = epoch + timedelta(hours=1)
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session:
            first = await release_candidates(session, placed_before=before, after=start, limit=3)
            rest = await release_candidates(session, placed_before=before, after=first[-1], limit=3)
    assert [order_id for _, order_id in first + rest] == due
    assert not any("FOR UPDATE" in s for s in statements), statements


async def test_the_owned_order_lock_is_for_update_and_owner_only(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_order(db_session, placed_at=EPOCH)
    stranger = await create_user(db_session)
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            store = SqlOrderStore(session)
            mine = await store.lock_owned_order(order.order_id, order.user_id)
            theirs = await store.lock_owned_order(order.order_id, stranger.id)
    assert mine is not None and mine.id == order.order_id and theirs is None
    assert all(s.endswith("FOR UPDATE") and "orders.user_id" in s for s in statements)


async def test_set_cancelled_writes_only_the_first_time(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_order(db_session, placed_at=EPOCH)
    for at in (AT, AT + timedelta(hours=1)):
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await SqlOrderStore(session).set_cancelled(order.order_id, at=at)
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).cancelled_at == AT
