"""The database guarantees behind the cart (VS-022 plan §4, §6): each constraint is
hit directly with SQL, independent of the application path."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.identity.infrastructure.models import UserModel
from app.identity.infrastructure.repositories import UserRepository
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

pytestmark = pytest.mark.integration


async def _refusal(engine: AsyncEngine, sql: str, **params: object) -> tuple[str, str] | None:
    """Run one statement in a rolled-back transaction; (SQLSTATE, constraint), or None."""
    async with engine.connect() as conn:
        try:
            await conn.execute(text(sql), params)
        except DBAPIError as exc:
            cause = getattr(exc.orig, "__cause__", None)
            return (
                str(getattr(exc.orig, "sqlstate", None)),
                str(getattr(cause, "constraint_name", None)),
            )
        finally:
            await conn.rollback()
    return None


async def _cart_with_line(
    db: AsyncSession, engine: AsyncEngine
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await create_user(db)
    refs = await seed_refs(db)
    physical = await seed_product(db, refs)
    stl = await seed_product(db, refs, type=ProductType.STL)
    async with engine.begin() as conn:
        cart_id = await conn.scalar(
            text("INSERT INTO carts (user_id) VALUES (:u) RETURNING id"), {"u": user.id}
        )
        await conn.execute(
            text(
                "INSERT INTO cart_items (cart_id, product_id, product_type, quantity, "
                "price_snapshot_cents) VALUES (:c, :p, 'physical', 2, 1000)"
            ),
            {"c": cart_id, "p": physical.id},
        )
    assert cart_id is not None
    return user.id, cart_id, physical.id, stl.id


_INSERT_LINE = (
    "INSERT INTO cart_items (cart_id, product_id, product_type, quantity, "
    "price_snapshot_cents, currency) VALUES (:c, :p, :t, :q, :cents, :cur)"
)


@pytest.mark.parametrize(
    ("product", "product_type", "quantity", "cents", "currency", "refusal"),
    [
        ("physical", "physical", 1, 1000, "USD", ("23505", "uq_cart_items_cart_product")),
        ("stl", "stl", 2, 1000, "USD", ("23514", "ck_cart_items_stl_quantity_one")),
        ("stl", "stl", 0, 1000, "USD", ("23514", "ck_cart_items_quantity_positive")),
        ("stl", "stl", 1, -1, "USD", ("23514", "ck_cart_items_price_snapshot_non_negative")),
        ("stl", "stl", 1, 1000, "EUR", ("23514", "ck_cart_items_currency_usd")),
        ("stl", "physical", 1, 1000, "USD", ("23503", "fk_cart_items_product_type")),
    ],
)
async def test_the_database_refuses_invalid_lines(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    product: str,
    product_type: str,
    quantity: int,
    cents: int,
    currency: str,
    refusal: tuple[str, str],
) -> None:
    _, cart_id, physical_id, stl_id = await _cart_with_line(db_session, db_engine)
    params = {
        "c": cart_id,
        "p": physical_id if product == "physical" else stl_id,
        "t": product_type,
        "q": quantity,
        "cents": cents,
        "cur": currency,
    }
    assert await _refusal(db_engine, _INSERT_LINE, **params) == refusal


async def test_a_valid_stl_line_is_accepted(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _, cart_id, _, stl_id = await _cart_with_line(db_session, db_engine)
    params = {"c": cart_id, "p": stl_id, "t": "stl", "q": 1, "cents": 0, "cur": "USD"}
    assert await _refusal(db_engine, _INSERT_LINE, **params) is None


async def test_one_cart_per_user(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    user_id, *_ = await _cart_with_line(db_session, db_engine)
    sql = "INSERT INTO carts (user_id) VALUES (:u)"
    assert await _refusal(db_engine, sql, u=user_id) == ("23505", "uq_carts_user_id")


# A valid STL row: every physical-only field cleared, so only the composite FK can refuse.
_TO_VALID_STL = (
    "UPDATE products SET type = 'stl', purchase_mode = NULL, accepted_payment_methods = NULL, "
    "material_id = NULL, "
    "colour_id = NULL, dimensions = NULL, production_lead_time_days = NULL, "
    "batch_size = NULL, max_quantity_per_line = NULL, weight_grams = NULL WHERE id = :p"
)


async def test_a_product_in_a_cart_cannot_change_type(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Two layers: a bare type change breaks the type CHECK first; a change that is a
    valid STL row is stopped by the composite FK, the backstop (ADR-029)."""
    _, _, physical_id, _ = await _cart_with_line(db_session, db_engine)
    bare = "UPDATE products SET type = 'stl' WHERE id = :p"
    assert await _refusal(db_engine, bare, p=physical_id) == (
        "23514",
        "ck_products_type_integrity",
    )
    assert await _refusal(db_engine, _TO_VALID_STL, p=physical_id) == (
        "23503",
        "fk_cart_items_product_type",
    )


async def test_a_product_in_a_cart_cannot_be_hard_deleted(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _, _, physical_id, _ = await _cart_with_line(db_session, db_engine)
    sql = "DELETE FROM products WHERE id = :p"
    assert await _refusal(db_engine, sql, p=physical_id) == ("23503", "fk_cart_items_product_type")


async def test_the_never_verified_purge_cascades_through_the_cart(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user_id, cart_id, _, _ = await _cart_with_line(db_session, db_engine)
    old = datetime.now(UTC) - timedelta(days=365)
    await db_session.execute(
        update(UserModel)
        .where(UserModel.id == user_id)
        .values(email_verified_at=None, created_at=old)
    )
    await db_session.commit()

    async with AsyncSession(db_engine) as session, session.begin():
        await UserRepository(session).purge_never_verified_before(old + timedelta(days=1))

    async with db_engine.connect() as conn:
        carts = await conn.scalar(text("SELECT count(*) FROM carts WHERE id = :c"), {"c": cart_id})
        lines = await conn.scalar(
            text("SELECT count(*) FROM cart_items WHERE cart_id = :c"), {"c": cart_id}
        )
    assert (carts, lines) == (0, 0)
