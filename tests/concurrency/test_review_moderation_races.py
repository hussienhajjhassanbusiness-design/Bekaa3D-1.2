"""VS-037 plan 6.3: hide / restore races on real Postgres. Moderation takes no `R_user`, so
the gate is the review row, held from outside; racers queue on it (or on the product lock
behind it) in start order, so the first racer listed commits first. No run may deadlock."""

import asyncio
import random
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.engagement.application.commands.custom_request_pipeline import AdminContext
from app.engagement.application.services.review_moderation import moderate_review
from app.engagement.domain.exceptions import ReviewModerationConflictError, ReviewNotFoundError
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.identity.domain.enums import UserRole
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.test_review_races import (
    RACE_TIMEOUT_SECONDS,
    REPEATS,
    World,
    together,
)
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.engagement.review_support import (
    fresh_totals,
    product_of_line,
    review_row,
    stored_totals,
)
from tests.integration.payments.refund_support import paid_online

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
Racer = Callable[[], Coroutine[Any, Any, str]]


@pytest.fixture
async def world(db_engine: AsyncEngine, db_session: AsyncSession) -> World:
    return World(db_engine, (await create_user(db_session, role=UserRole.ADMIN)).id)


@asynccontextmanager
async def _held_review(engine: AsyncEngine, review_id: uuid.UUID) -> AsyncIterator[Any]:
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT id FROM reviews WHERE id = :r FOR UPDATE"), {"r": review_id}
        )
        try:
            yield conn
        finally:
            await conn.rollback()


async def _lock_waiters(engine: AsyncEngine, count: int, seconds: float = 10.0) -> None:
    """Block until `count` backends wait on a heavyweight lock, or fail."""
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database()"
                )
            )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"fewer than {count} transactions ever waited on a lock")


async def queued_on_review(engine: AsyncEngine, review_id: uuid.UUID, *racers: Racer) -> list[str]:
    """Each racer starts once the one before it waits; they commit in that order."""
    async with _held_review(engine, review_id) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            await _lock_waiters(engine, n)
        await held.rollback()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)


def moderate(world: World, review_id: uuid.UUID, *, hide: bool) -> Racer:
    async def work(session: AsyncSession) -> str:
        try:
            await moderate_review(
                SqlReviewStore(session),
                CatalogReviewableProducts(session),
                SqlAuditWriter(session),
                review_id=review_id,
                hide=hide,
                reason="race",
                now=datetime.now(UTC),
                context=AdminContext(world.admin, None, None),
            )
        except ReviewNotFoundError:
            return "missing"
        except ReviewModerationConflictError:
            return "conflict"
        return "hidden" if hide else "restored"

    return lambda: world._tx(work)


async def _audit_actions(engine: AsyncEngine, review_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text(
                "SELECT action FROM audit_logs WHERE entity_type = 'review' AND entity_id = :r"
                " ORDER BY created_at"
            ),
            {"r": review_id},
        )
        return list(rows)


async def _assert_exact(engine: AsyncEngine, product_id: uuid.UUID) -> None:
    assert await stored_totals(engine, product_id) == await fresh_totals(engine, product_id)


async def _reviewed_product(
    world: World, db: AsyncSession, *ratings: int
) -> tuple[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    product = await seed_product(db, await seed_refs(db))
    out = []
    for rating in ratings:
        author = (await create_user(db)).id
        created = await world.create(author, product.id, rating)()
        out.append((author, uuid.UUID(created.split(":")[1])))
    return product.id, out


# --- M1: hide vs author edit -----------------------------------------------------------------


@pytest.mark.parametrize("hide_first", [True, False])
async def test_m1_hide_vs_author_edit(
    hide_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        product_id, [(author, review), _other] = await _reviewed_product(world, db_session, 1, 3)
        hide = moderate(world, review, hide=True)
        edit = world.edit(author, review, 5)
        racers = (hide, edit) if hide_first else (edit, hide)
        assert sorted(await queued_on_review(db_engine, review, *racers)) == ["edited", "hidden"]
        row = await review_row(db_engine, review)
        assert (row.is_hidden, row.rating) == (True, 5)
        assert await stored_totals(db_engine, product_id) == (Decimal("3.00"), 1)
        await _assert_exact(db_engine, product_id)


# --- M2: hide vs author delete ---------------------------------------------------------------


@pytest.mark.parametrize("hide_first", [True, False])
async def test_m2_hide_vs_author_delete(
    hide_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        product_id, [(author, review), _other] = await _reviewed_product(world, db_session, 1, 4)
        hide = moderate(world, review, hide=True)
        delete = world.delete(author, review)
        racers = (hide, delete) if hide_first else (delete, hide)
        results = await queued_on_review(db_engine, review, *racers)
        row = await review_row(db_engine, review)
        assert row.deleted_at is not None
        if hide_first:
            assert results == ["hidden", "deleted"]
            assert row.is_hidden is True
            assert await _audit_actions(db_engine, review) == ["review.hidden"]
        else:
            assert results == ["deleted", "missing"]
            assert row.is_hidden is False
            assert await _audit_actions(db_engine, review) == []
        assert await stored_totals(db_engine, product_id) == (Decimal("4.00"), 1)
        await _assert_exact(db_engine, product_id)


# --- M3: hide vs hide ----------------------------------------------------------------------


async def test_m3_hide_vs_hide_is_one_success_and_one_conflict(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        product_id, [(_a, review), _other] = await _reviewed_product(world, db_session, 2, 5)
        first, second = moderate(world, review, hide=True), moderate(world, review, hide=True)
        assert await queued_on_review(db_engine, review, first, second) == ["hidden", "conflict"]
        assert await _audit_actions(db_engine, review) == ["review.hidden"]
        assert await stored_totals(db_engine, product_id) == (Decimal("5.00"), 1)
        await _assert_exact(db_engine, product_id)


# --- M4: hide vs restore -------------------------------------------------------------------


@pytest.mark.parametrize("hide_first", [True, False])
async def test_m4_hide_vs_restore_of_a_visible_review(
    hide_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        product_id, [(_a, review), _other] = await _reviewed_product(world, db_session, 1, 5)
        hide, restore = moderate(world, review, hide=True), moderate(world, review, hide=False)
        racers = (hide, restore) if hide_first else (restore, hide)
        results = await queued_on_review(db_engine, review, *racers)
        hidden = (await review_row(db_engine, review)).is_hidden
        if hide_first:
            assert results == ["hidden", "restored"] and hidden is False
            assert await _audit_actions(db_engine, review) == ["review.hidden", "review.restored"]
            assert await stored_totals(db_engine, product_id) == (Decimal("3.00"), 2)
        else:
            assert results == ["conflict", "hidden"] and hidden is True
            assert await _audit_actions(db_engine, review) == ["review.hidden"]
            assert await stored_totals(db_engine, product_id) == (Decimal("5.00"), 1)
        await _assert_exact(db_engine, product_id)


# --- M5: aggregates exact under a mixed load -------------------------------------------------


async def test_m5_mixed_moderation_and_author_writes_keep_the_aggregates_exact(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    rng = random.Random(37)
    for _ in range(REPEATS):
        ratings = [rng.randint(1, 5) for _ in range(10)]
        product_id, reviews = await _reviewed_product(world, db_session, *ratings)
        for _author, review in reviews[3:5]:
            assert await moderate(world, review, hide=True)() == "hidden"
        newcomer = (await create_user(db_session)).id
        racers = [moderate(world, r, hide=True) for _a, r in reviews[:3]]
        racers += [moderate(world, r, hide=False) for _a, r in reviews[3:5]]
        racers += [world.edit(a, r, rng.randint(1, 5)) for a, r in reviews[5:7]]
        racers += [world.delete(*reviews[7]), world.create(newcomer, product_id, 4)]
        results = await together(*racers)
        assert sorted(r.split(":")[0] for r in results) == sorted(
            ["hidden"] * 3 + ["restored"] * 2 + ["edited"] * 2 + ["deleted", "created"]
        )
        await _assert_exact(db_engine, product_id)
        assert (await stored_totals(db_engine, product_id))[1] == 7


# --- M6: hide vs the badge hook --------------------------------------------------------------


@pytest.mark.parametrize("refund_first", [True, False])
async def test_m6_hide_vs_a_refund_whose_hook_flips_the_badge(
    refund_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        order = await paid_online(db_session, stl=None)
        line = order.physical[0]
        product_id = await product_of_line(db_engine, line)
        created = await world.create(order.user_id, product_id, 4)()
        review = uuid.UUID(created.split(":")[1])
        assert (await review_row(db_engine, review)).is_verified_purchase is True
        refund = world.refund(order.order_id, line, 1000)
        hide = moderate(world, review, hide=True)
        racers = (refund, hide) if refund_first else (hide, refund)
        assert sorted(await queued_on_review(db_engine, review, *racers)) == [
            "hidden",
            "refunded",
        ]
        row = await review_row(db_engine, review)
        assert (row.is_verified_purchase, row.is_hidden) == (False, True)
        assert await stored_totals(db_engine, product_id) == (Decimal("0.00"), 0)
        await _assert_exact(db_engine, product_id)
