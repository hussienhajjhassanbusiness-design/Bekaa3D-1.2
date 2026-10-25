"""VS-036 PR A on real Postgres (migration eeed201dcfd2, plan 4.2): every `reviews` constraint
refuses its row by name, and the same statement passes once that constraint alone is dropped
(in a rolled-back transaction). No application code writes `reviews` yet."""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

pytestmark = pytest.mark.integration

_INSERT = (
    "INSERT INTO reviews (user_id, product_id, rating, body, is_hidden, hidden_at, deleted_at,"
    " created_at, updated_at) VALUES (:user_id, :product_id, :rating, :body, :is_hidden,"
    " :hidden_at, :deleted_at, :created_at, :updated_at)"
)


def constraint_of(error: IntegrityError) -> str | None:
    """asyncpg's `constraint_name` for the refusal."""
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


async def assert_refused(
    engine: AsyncEngine,
    constraint: str,
    sql: str,
    params: Mapping[str, Any],
    *,
    drop: str,
    setup: str | None = None,
) -> None:
    """Refused by `constraint` (by name), then accepted once `drop` removes it; all rolled back."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            if setup is not None:
                await conn.execute(text(setup), dict(params))
            with pytest.raises(IntegrityError) as caught:
                async with conn.begin_nested():
                    await conn.execute(text(sql), dict(params))
            assert constraint_of(caught.value) == constraint, caught.value
            await conn.execute(text(drop))
            await conn.execute(text(sql), dict(params))  # the scratch proof
        finally:
            await outer.rollback()


async def _subjects(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user = await create_user(db)
    product = await seed_product(db, await seed_refs(db), type=ProductType.STL)
    return user.id, product.id


def _row(user_id: uuid.UUID, product_id: uuid.UUID, **over: Any) -> dict[str, Any]:
    at = datetime.now(UTC)
    values: dict[str, Any] = {
        "user_id": user_id,
        "product_id": product_id,
        "rating": 4,
        "body": "Prints cleanly.",
        "is_hidden": False,
        "hidden_at": None,
        "deleted_at": None,
        "created_at": at,
        "updated_at": at,
    }
    return values | over


def _drop(name: str) -> str:
    return f"ALTER TABLE reviews DROP CONSTRAINT {name}"


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _accept(conn: AsyncConnection, row: Mapping[str, Any]) -> None:
    await conn.execute(text(_INSERT), dict(row))


async def test_valid_rows_are_accepted(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    user_id, product_id = await _subjects(db_session)
    other_user = (await create_user(db_session)).id
    hidden_at = datetime.now(UTC)
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        try:
            await _accept(conn, _row(user_id, product_id, body=None, rating=1))
            await _accept(
                conn,
                _row(
                    other_user,
                    product_id,
                    rating=5,
                    body="x" * 2000,
                    is_hidden=True,
                    hidden_at=hidden_at,
                ),
            )
            defaults = await conn.execute(
                text(
                    "SELECT is_verified_purchase, is_hidden, hidden_at FROM reviews"
                    " WHERE user_id = :u AND product_id = :p"
                ),
                {"u": user_id, "p": product_id},
            )
            assert defaults.one() == (False, False, None)
        finally:
            await outer.rollback()


@pytest.mark.parametrize("rating", [0, 6, -1])
async def test_ck_reviews_rating_range(
    rating: int, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    await assert_refused(
        db_engine,
        "ck_reviews_rating_range",
        _INSERT,
        _row(user_id, product_id, rating=rating),
        drop=_drop("ck_reviews_rating_range"),
    )


@pytest.mark.parametrize("body", ["", "   ", "x" * 2001])
async def test_ck_reviews_body_shape(
    body: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    await assert_refused(
        db_engine,
        "ck_reviews_body_shape",
        _INSERT,
        _row(user_id, product_id, body=body),
        drop=_drop("ck_reviews_body_shape"),
    )


@pytest.mark.parametrize(
    ("is_hidden", "hidden_at"), [(True, None), (False, datetime(2026, 10, 25, tzinfo=UTC))]
)
async def test_ck_reviews_hidden_shape(
    is_hidden: bool, hidden_at: datetime | None, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    await assert_refused(
        db_engine,
        "ck_reviews_hidden_shape",
        _INSERT,
        _row(user_id, product_id, is_hidden=is_hidden, hidden_at=hidden_at),
        drop=_drop("ck_reviews_hidden_shape"),
    )


async def test_ck_reviews_updated_after_created(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    at = datetime.now(UTC)
    await assert_refused(
        db_engine,
        "ck_reviews_updated_after_created",
        _INSERT,
        _row(user_id, product_id, created_at=at, updated_at=at - timedelta(seconds=1)),
        drop=_drop("ck_reviews_updated_after_created"),
    )


async def test_uq_reviews_user_product_live_refuses_a_second_live_review(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """A hidden review is live, so it blocks a second one too (plan D8)."""
    user_id, product_id = await _subjects(db_session)
    hidden_first = (
        "INSERT INTO reviews (user_id, product_id, rating, is_hidden, hidden_at)"
        " VALUES (:user_id, :product_id, 3, true, now())"
    )
    await assert_refused(
        db_engine,
        "uq_reviews_user_product_live",
        _INSERT,
        _row(user_id, product_id),
        drop="DROP INDEX uq_reviews_user_product_live",
        setup=hidden_first,
    )


async def test_a_deleted_review_frees_the_pair(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        try:
            await _accept(conn, _row(user_id, product_id, deleted_at=datetime.now(UTC)))
            await _accept(conn, _row(user_id, product_id, deleted_at=datetime.now(UTC)))
            await _accept(conn, _row(user_id, product_id))
        finally:
            await outer.rollback()


@pytest.mark.parametrize("column", ["user_id", "product_id"])
async def test_fk_reviews_refuses_an_unknown_parent(
    column: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id, product_id = await _subjects(db_session)
    row = _row(user_id, product_id) | {column: uuid.uuid4()}
    await assert_refused(
        db_engine, f"fk_reviews_{column}", _INSERT, row, drop=_drop(f"fk_reviews_{column}")
    )


@pytest.mark.parametrize(("column", "parent"), [("user_id", "users"), ("product_id", "products")])
async def test_fk_reviews_restricts_deleting_the_parent(
    column: str, parent: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """RESTRICT (plan 4.2): a review keeps its author and product; reviews are history."""
    user_id, product_id = await _subjects(db_session)
    row = _row(user_id, product_id)
    target = {"users": user_id, "products": product_id}[parent]
    await assert_refused(
        db_engine,
        f"fk_reviews_{column}",
        f"DELETE FROM {parent} WHERE id = :target",
        row | {"target": target},
        drop=_drop(f"fk_reviews_{column}"),
        setup=_INSERT,
    )
    rule = await _scalar(
        db_engine,
        "SELECT confdeltype::text FROM pg_constraint WHERE conname = :n",
        n=f"fk_reviews_{column}",
    )
    assert rule == "r"


async def test_the_indexes_exist_with_their_predicates(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN"
                " ('uq_reviews_user_product_live', 'ix_reviews_product_visible',"
                " 'ix_reviews_user_live', 'ix_order_items_badge_received')"
            )
        )
        defs = dict(rows.all())
    assert set(defs) == {
        "uq_reviews_user_product_live",
        "ix_reviews_product_visible",
        "ix_reviews_user_live",
        "ix_order_items_badge_received",
    }
    assert "UNIQUE" in defs["uq_reviews_user_product_live"]
    assert (
        "(user_id, product_id) WHERE (deleted_at IS NULL)" in defs["uq_reviews_user_product_live"]
    )
    assert "(product_id, created_at DESC, id DESC)" in defs["ix_reviews_product_visible"]
    assert "(deleted_at IS NULL) AND (NOT is_hidden)" in defs["ix_reviews_product_visible"]
    assert (
        "(user_id, created_at DESC, id DESC) WHERE (deleted_at IS NULL)"
        in defs["ix_reviews_user_live"]
    )
    badge = defs["ix_order_items_badge_received"]
    assert "UNIQUE" not in badge
    assert "ON public.order_items USING btree (user_id, product_id)" in badge
    assert "product_type = 'physical'" in badge
    assert "'delivered'" in badge and "'picked_up'" in badge
    assert "'shipped'" not in badge and "'awaiting_delivery'" not in badge
