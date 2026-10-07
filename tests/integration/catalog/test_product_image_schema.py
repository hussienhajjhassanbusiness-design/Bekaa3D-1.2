"""`product_images` as migration cc87333ebe79 built it, refused by PostgreSQL itself."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.catalog.test_reference_schema import _constraint_name


def _key() -> str:
    return f"products/{uuid.uuid4()}.jpg"


def _row(**over: str) -> dict[str, str]:
    return {"storage_key": f"'{_key()}'", "sort_order": "0", "is_cover": "false"} | over


async def _refusal(db_engine: AsyncEngine, *rows: dict[str, str]) -> IntegrityError | None:
    """Insert images for one fresh product in a rolled-back transaction."""
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            category = await conn.scalar(
                text("INSERT INTO categories (name, slug) VALUES ('c', :s) RETURNING id"),
                {"s": f"c-{uuid.uuid4().hex[:12]}"},
            )
            product = await conn.scalar(
                text(
                    "INSERT INTO products (type, category_id, name, slug, price_cents) "
                    "VALUES ('stl', :c, 'p', :s, 1) RETURNING id"
                ),
                {"c": category, "s": f"p-{uuid.uuid4().hex[:12]}"},
            )
            for index, row in enumerate(rows):
                sql = (
                    f"INSERT INTO product_images (product_id, {', '.join(row)}) "
                    f"VALUES (:p, {', '.join(row.values())})"
                )
                try:
                    await conn.execute(text(sql), {"p": product})
                except IntegrityError as exc:
                    assert index == len(rows) - 1, f"row {index} refused early: {exc}"
                    return exc
            return None
        finally:
            await transaction.rollback()


@pytest.mark.integration
async def test_two_live_covers_are_refused(db_engine: AsyncEngine) -> None:
    """Done-when: a product never has two covers."""
    error = await _refusal(db_engine, _row(is_cover="true"), _row(is_cover="true"))
    assert error is not None
    assert _constraint_name(error) == "ix_product_images_live_cover"


@pytest.mark.integration
async def test_a_deleted_former_cover_does_not_block_a_new_one(db_engine: AsyncEngine) -> None:
    gone = _row(deleted_at="now()")
    assert await _refusal(db_engine, gone, _row(is_cover="true")) is None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("row", "constraint"),
    [
        (_row(is_cover="true", deleted_at="now()"), "ck_product_images_deleted_not_cover"),
        (_row(sort_order="-1"), "ck_product_images_sort_order_non_negative"),
        (_row(storage_key="'../../etc/passwd'"), "ck_product_images_storage_key_format"),
        (_row(storage_key="'products/photo.jpg'"), "ck_product_images_storage_key_format"),
        (_row(storage_key=f"'{_key().upper()}'"), "ck_product_images_storage_key_format"),
        (_row(storage_key=f"'{_key()[:-4]}.gif'"), "ck_product_images_storage_key_format"),
        (_row(storage_key=f"'/{_key()}'"), "ck_product_images_storage_key_format"),
    ],
    ids=[
        "deleted-cover",
        "negative-order",
        "traversal",
        "client-name",
        "uppercase",
        "gif",
        "absolute",
    ],
)
async def test_bad_rows_are_refused(
    db_engine: AsyncEngine, row: dict[str, str], constraint: str
) -> None:
    error = await _refusal(db_engine, row)
    assert error is not None, f"{row} was stored"
    assert _constraint_name(error) == constraint


@pytest.mark.integration
async def test_two_rows_never_share_a_file(db_engine: AsyncEngine) -> None:
    """Keeps the reaper's "is this file referenced?" answer sound."""
    key = f"'{_key()}'"
    error = await _refusal(
        db_engine, _row(storage_key=key, deleted_at="now()"), _row(storage_key=key)
    )
    assert error is not None
    assert _constraint_name(error) == "uq_product_images_storage_key"


@pytest.mark.integration
async def test_the_product_foreign_key_restricts_deletion(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT confdeltype::text FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = 'product_images'::regclass"
            )
        )
        assert [row[0] for row in rows] == ["r"]
