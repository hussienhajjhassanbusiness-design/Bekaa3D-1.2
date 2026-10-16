"""VS-022 / FR-05 concurrency (plan §5, §6): every cart write takes the cart row lock
first (`INSERT ... ON CONFLICT DO NOTHING`, then `SELECT ... FOR UPDATE`), so merges,
the cap, the line count and the first add itself serialise per cart."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal, overload
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.catalog.infrastructure.cart_product_reader import SqlCartProductReader
from app.ordering.application.services.cart import (
    add_item,
    read_cart,
    remove_item,
    set_item_quantity,
)
from app.ordering.domain.entities import MAX_CART_LINES, Cart
from app.ordering.domain.exceptions import OrderingDomainError
from app.ordering.infrastructure.carts import SqlCartStore
from app.ordering.infrastructure.models import CartItemModel, CartModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]


class _SyncedCarts(SqlCartStore):
    """Releases every racer at the cart lock together; `hold` keeps the winner inside
    its transaction a moment, so the loser really waits on its row."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier, hold: float) -> None:
        super().__init__(session)
        self._barrier, self._hold = barrier, hold

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[True]) -> Cart: ...

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[False]) -> Cart | None: ...

    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        await meet_or_fail(self._barrier)
        cart = await (
            super().lock(user_id, create=True) if create else super().lock(user_id, create=False)
        )
        await asyncio.sleep(self._hold)
        return cart


Op = Callable[[SqlCartStore, SqlCartProductReader], Awaitable[None]]


async def _race(engine: AsyncEngine, ops: list[Op], *, hold: float = 0.05) -> list[str]:
    """Run each op in its own transaction; 'ok' or the domain error's class name.
    Anything else (an IntegrityError, a deadlock) propagates and fails the test."""
    barrier = asyncio.Barrier(len(ops))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def one(op: Op) -> str:
        try:
            async with factory() as db, db.begin():
                await op(_SyncedCarts(db, barrier, hold), SqlCartProductReader(db))
        except OrderingDomainError as exc:
            return type(exc).__name__
        return "ok"

    return list(await asyncio.gather(*(one(op) for op in ops)))


def _adding(user_id: UUID, product_id: UUID, quantity: int = 1) -> Op:
    async def op(carts: SqlCartStore, products: SqlCartProductReader) -> None:
        await add_item(carts, products, user_id=user_id, product_id=product_id, quantity=quantity)

    return op


async def _user(engine: AsyncEngine) -> UUID:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        return (await create_user(db)).id


async def _products(engine: AsyncEngine, n: int, **over: Any) -> list[UUID]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        refs = await seed_refs(db)
        return [(await seed_product(db, refs, **over)).id for _ in range(n)]


async def _state(engine: AsyncEngine, user_id: UUID) -> tuple[int, dict[UUID, int]]:
    """(number of carts, {product_id: quantity}) for the user."""
    async with engine.connect() as conn:
        carts = await conn.scalar(select(func.count()).where(CartModel.user_id == user_id))
        rows = await conn.execute(
            select(CartItemModel.product_id, CartItemModel.quantity)
            .join(CartModel, CartModel.id == CartItemModel.cart_id)
            .where(CartModel.user_id == user_id)
        )
        return int(carts or 0), {r.product_id: r.quantity for r in rows}


# ------------------------------------------------------- the first add (plan Rev. 1 #2)


@pytest.mark.parametrize("run", range(20))
async def test_two_concurrent_first_adds_both_succeed_into_one_cart(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    first, second = await _products(db_engine, 2)
    results = await _race(db_engine, [_adding(user_id, first), _adding(user_id, second)])
    assert results == ["ok", "ok"]
    assert await _state(db_engine, user_id) == (1, {first: 1, second: 1})


@pytest.mark.parametrize("run", range(20))
async def test_a_first_add_that_rolls_back_still_lets_the_other_create_the_cart(
    db_engine: AsyncEngine, run: int
) -> None:
    """The refused add (an unknown product: 422 after its INSERT) rolls back the cart
    row the other may be waiting on; the other then inserts it itself."""
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1)
    results = await _race(db_engine, [_adding(user_id, uuid4()), _adding(user_id, product)])
    assert results == ["ProductNotPurchasableError", "ok"]
    assert await _state(db_engine, user_id) == (1, {product: 1})


@pytest.mark.parametrize("run", range(5))
async def test_n_concurrent_first_adds_of_one_product_merge_into_one_line(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1, max_quantity_per_line=10)
    results = await _race(db_engine, [_adding(user_id, product) for _ in range(5)], hold=0.01)
    assert results == ["ok"] * 5
    assert await _state(db_engine, user_id) == (1, {product: 5})


# ------------------------------------------------------------ merges and the cap


@pytest.mark.parametrize("run", range(10))
async def test_two_concurrent_adds_of_one_product_stay_within_the_cap(
    db_engine: AsyncEngine, run: int
) -> None:
    """The plan row's named test: +3 and +3 against a cap of 5 - one line of 3."""
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1, max_quantity_per_line=5)
    results = await _race(db_engine, [_adding(user_id, product, 3), _adding(user_id, product, 3)])
    assert sorted(results) == ["QuantityExceedsLimitError", "ok"]
    assert await _state(db_engine, user_id) == (1, {product: 3})


@pytest.mark.parametrize("run", range(5))
async def test_n_concurrent_increments_stop_exactly_at_the_cap(
    db_engine: AsyncEngine, run: int
) -> None:
    n = 6
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1, max_quantity_per_line=n - 1)
    results = await _race(db_engine, [_adding(user_id, product) for _ in range(n)], hold=0.01)
    assert sorted(results) == ["QuantityExceedsLimitError"] + ["ok"] * (n - 1)
    assert await _state(db_engine, user_id) == (1, {product: n - 1})


@pytest.mark.parametrize("run", range(5))
async def test_concurrent_adds_of_one_stl_leave_one_line_of_one(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    [stl] = await _products(db_engine, 1, type=ProductType.STL)
    results = await _race(db_engine, [_adding(user_id, stl) for _ in range(4)], hold=0.01)
    assert results == ["ok"] * 4
    assert await _state(db_engine, user_id) == (1, {stl: 1})


@pytest.mark.parametrize("run", range(5))
async def test_the_fiftieth_line_goes_to_exactly_one_of_two_racers(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    products = await _products(db_engine, MAX_CART_LINES + 1, type=ProductType.STL)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    for product in products[: MAX_CART_LINES - 1]:
        async with factory() as db, db.begin():
            reader = SqlCartProductReader(db)
            await add_item(
                SqlCartStore(db), reader, user_id=user_id, product_id=product, quantity=1
            )
    results = await _race(
        db_engine, [_adding(user_id, products[-2]), _adding(user_id, products[-1])]
    )
    assert sorted(results) == ["CartLineLimitReachedError", "ok"]
    assert len((await _state(db_engine, user_id))[1]) == MAX_CART_LINES


# ------------------------------------------------------- other overlapping writes


@pytest.mark.parametrize("run", range(5))
async def test_concurrent_patch_and_delete_of_one_line_end_consistently(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        reader = SqlCartProductReader(db)
        await add_item(SqlCartStore(db), reader, user_id=user_id, product_id=product, quantity=1)

    async def patch(carts: SqlCartStore, products: SqlCartProductReader) -> None:
        await set_item_quantity(carts, products, user_id=user_id, product_id=product, quantity=4)

    async def delete(carts: SqlCartStore, products: SqlCartProductReader) -> None:
        await remove_item(carts, user_id=user_id, product_id=product)

    results = await _race(db_engine, [patch, delete])
    _, lines = await _state(db_engine, user_id)
    if results == ["ok", "ok"]:
        assert lines == {}  # the patch committed first, then the delete
    else:
        assert results == ["CartLineNotFoundError", "ok"]
        assert lines == {}
    async with factory() as db:
        view = await read_cart(SqlCartStore(db), SqlCartProductReader(db), user_id=user_id)
    assert view.lines == ()


@pytest.mark.parametrize("run", range(5))
async def test_an_add_racing_a_price_change_snapshots_one_of_the_two_prices(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id = await _user(db_engine)
    [product] = await _products(db_engine, 1, price_cents=1000)
    barrier = asyncio.Barrier(2)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def add() -> None:
        async with factory() as db, db.begin():
            await add_item(
                _SyncedCarts(db, barrier, 0.0),
                SqlCartProductReader(db),
                user_id=user_id,
                product_id=product,
                quantity=1,
            )

    async def reprice() -> None:
        async with db_engine.begin() as conn:
            await meet_or_fail(barrier)
            await conn.execute(
                text("UPDATE products SET price_cents = 2000 WHERE id = :p"), {"p": product}
            )

    await asyncio.gather(add(), reprice())
    async with factory() as db:
        view = await read_cart(SqlCartStore(db), SqlCartProductReader(db), user_id=user_id)
    [line] = view.lines
    assert line.line.price_snapshot_cents in (1000, 2000)
    assert line.current_price_cents == 2000
    assert line.price_changed is (line.line.price_snapshot_cents == 1000)
