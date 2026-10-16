"""VS-038 / FR-14: concurrent wishlist writes must never leave `wishlist_count`
disagreeing with the number of live `wishlist_items` rows. The insert-only
`add` (one `INSERT ... ON CONFLICT ... DO NOTHING RETURNING id`) and `remove`
(one `UPDATE ... RETURNING id`) are each a single atomic statement, so the
barrier below only needs to force genuinely overlapping arrivals at that one
statement - there is no read-then-write window for a stale read to open."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.infrastructure.models import ProductModel
from app.catalog.infrastructure.product_repository import ProductRepository
from app.engagement.application.services.wishlist import add_to_wishlist, remove_from_wishlist
from app.engagement.infrastructure.models import WishlistItemModel
from app.engagement.infrastructure.wishlist import SqlWishlistCounter, SqlWishlistRepository
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]


class _SyncedRepository(SqlWishlistRepository):
    """Wraps the one atomic statement each of `add`/`remove` issues with a
    barrier, so every racer reaches Postgres together rather than relying on
    `asyncio.gather` scheduling to happen to overlap them."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def add(self, *, user_id: UUID, product_id: UUID) -> bool:
        await meet_or_fail(self._barrier)
        return await super().add(user_id=user_id, product_id=product_id)

    async def remove(self, *, user_id: UUID, product_id: UUID) -> bool:
        await meet_or_fail(self._barrier)
        return await super().remove(user_id=user_id, product_id=product_id)


async def _seed_product(engine: AsyncEngine) -> UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        refs = await seed_refs(db)
        product = await seed_product(db, refs)
    return product.id


async def _wishlist_count(engine: AsyncEngine, product_id: UUID) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        return (
            await db.scalar(
                select(ProductModel.wishlist_count).where(ProductModel.id == product_id)
            )
            or 0
        )


async def _active_row_count(engine: AsyncEngine, product_id: UUID) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        return int(
            await db.scalar(
                select(func.count())
                .select_from(WishlistItemModel)
                .where(
                    WishlistItemModel.product_id == product_id,
                    WishlistItemModel.deleted_at.is_(None),
                )
            )
            or 0
        )


async def _add(
    engine: AsyncEngine, barrier: asyncio.Barrier, *, user_id: UUID, product_id: UUID
) -> bool:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        changed = await add_to_wishlist(
            _SyncedRepository(db, barrier),
            ProductRepository(db),
            SqlWishlistCounter(db),
            user_id=user_id,
            product_id=product_id,
        )
    return changed


async def _remove(
    engine: AsyncEngine, barrier: asyncio.Barrier, *, user_id: UUID, product_id: UUID
) -> bool:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        changed = await remove_from_wishlist(
            _SyncedRepository(db, barrier),
            SqlWishlistCounter(db),
            user_id=user_id,
            product_id=product_id,
        )
    return changed


@pytest.mark.parametrize("run", range(3))
async def test_n_concurrent_adds_for_the_same_pair_leave_one_row_and_increment_once(
    db_engine: AsyncEngine, run: int
) -> None:
    product_id = await _seed_product(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user_id = (await create_user(db)).id
    n = 5
    barrier = asyncio.Barrier(n)

    results = await asyncio.gather(
        *(_add(db_engine, barrier, user_id=user_id, product_id=product_id) for _ in range(n))
    )

    assert sum(results) == 1, "exactly one racer should have inserted the row"
    assert await _active_row_count(db_engine, product_id) == 1
    assert await _wishlist_count(db_engine, product_id) == 1


async def test_two_concurrent_adds_on_a_previously_removed_product(db_engine: AsyncEngine) -> None:
    """The case the insert-only redesign specifically targets: no conflicting
    *active* row exists (the earlier one is soft-deleted), so both racers'
    `INSERT ... ON CONFLICT` statements genuinely compete for the same arbiter
    index entry - not for an already-settled row."""
    product_id = await _seed_product(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user_id = (await create_user(db)).id
        db.add(WishlistItemModel(user_id=user_id, product_id=product_id, deleted_at=func.now()))
        await db.commit()
    before = await _wishlist_count(db_engine, product_id)
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        *(_add(db_engine, barrier, user_id=user_id, product_id=product_id) for _ in range(2))
    )

    assert sum(results) == 1
    assert await _active_row_count(db_engine, product_id) == 1
    assert await _wishlist_count(db_engine, product_id) == before + 1


async def test_concurrent_add_and_remove_leave_a_consistent_final_state(
    db_engine: AsyncEngine,
) -> None:
    product_id = await _seed_product(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user_id = (await create_user(db)).id
        db.add(WishlistItemModel(user_id=user_id, product_id=product_id))
        # Seeded directly, bypassing adjust_wishlist_count - the counter must
        # match the row it is standing in for, or this test would be
        # asserting against its own broken fixture, not the app's invariant.
        await db.execute(
            update(ProductModel).where(ProductModel.id == product_id).values(wishlist_count=1)
        )
        await db.commit()
    barrier = asyncio.Barrier(2)

    await asyncio.gather(
        _add(db_engine, barrier, user_id=user_id, product_id=product_id),
        _remove(db_engine, barrier, user_id=user_id, product_id=product_id),
    )

    active = await _active_row_count(db_engine, product_id)
    count = await _wishlist_count(db_engine, product_id)
    assert count == active, "wishlist_count must never drift from the live row count"
    assert active in (0, 1)


async def test_concurrent_adds_for_the_same_user_different_products_are_independent(
    db_engine: AsyncEngine,
) -> None:
    product_a = await _seed_product(db_engine)
    product_b = await _seed_product(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user_id = (await create_user(db)).id
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        _add(db_engine, barrier, user_id=user_id, product_id=product_a),
        _add(db_engine, barrier, user_id=user_id, product_id=product_b),
    )

    assert list(results) == [True, True]
    assert await _wishlist_count(db_engine, product_a) == 1
    assert await _wishlist_count(db_engine, product_b) == 1


async def test_many_users_racing_add_remove_readd_on_one_product_keeps_the_counter_exact(
    db_engine: AsyncEngine,
) -> None:
    """The general form of the plan's "Done when" line: not just two callers,
    not just one action type. Some users are adding for the first time, some
    are removing an existing entry, some are re-adding after a prior removal."""
    product_id = await _seed_product(db_engine)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as db:
        users = [await create_user(db) for _ in range(12)]
        fresh_users = [u.id for u in users[:4]]
        removing_users = [u.id for u in users[4:8]]
        readding_users = [u.id for u in users[8:12]]
        for uid in removing_users:
            db.add(WishlistItemModel(user_id=uid, product_id=product_id))
        for uid in readding_users:
            db.add(WishlistItemModel(user_id=uid, product_id=product_id, deleted_at=func.now()))
        # The seeded active rows (removing_users) bypass adjust_wishlist_count,
        # so the counter is corrected to match them before racing - otherwise
        # this test would be proving something about a self-inconsistent
        # fixture, not the app's invariant.
        await db.execute(
            update(ProductModel)
            .where(ProductModel.id == product_id)
            .values(wishlist_count=len(removing_users))
        )
        await db.commit()

    n = len(fresh_users) + len(removing_users) + len(readding_users)
    barrier = asyncio.Barrier(n)
    tasks = (
        [_add(db_engine, barrier, user_id=uid, product_id=product_id) for uid in fresh_users]
        + [
            _remove(db_engine, barrier, user_id=uid, product_id=product_id)
            for uid in removing_users
        ]
        + [_add(db_engine, barrier, user_id=uid, product_id=product_id) for uid in readding_users]
    )

    await asyncio.gather(*tasks)

    active = await _active_row_count(db_engine, product_id)
    count = await _wishlist_count(db_engine, product_id)
    assert count == active
