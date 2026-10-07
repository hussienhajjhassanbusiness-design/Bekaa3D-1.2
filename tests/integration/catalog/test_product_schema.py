"""`products` as migration fc18b48a1780 built it: every rule is refused by PostgreSQL
itself, through raw SQL, so no application check is standing in for a constraint."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.catalog.test_reference_schema import _constraint_name

PHYSICAL_ONLY = {
    "purchase_mode": "'both'",
    "material_id": ":material_id",
    "colour_id": ":colour_id",
    "dimensions": """'{"length_mm": 1, "width_mm": 1, "height_mm": 1}'""",
    "production_lead_time_days": "2",
    "batch_size": "1",
    "max_quantity_per_line": "1",
    "weight_grams": "10",
}
PHYSICAL_REQUIRED = (
    "purchase_mode",
    "production_lead_time_days",
    "batch_size",
    "max_quantity_per_line",
)


def _stl() -> dict[str, str]:
    return {
        "type": "'stl'",
        "category_id": ":category_id",
        "name": "'Dragon'",
        "slug": f"'p-{uuid.uuid4().hex[:12]}'",
        "price_cents": "100",
    }


def _physical() -> dict[str, str]:
    return _stl() | {"type": "'physical'"} | {k: PHYSICAL_ONLY[k] for k in PHYSICAL_REQUIRED}


def _insert_sql(row: dict[str, str]) -> str:
    return f"INSERT INTO products ({', '.join(row)}) VALUES ({', '.join(row.values())})"


async def _refusal(db_engine: AsyncEngine, *rows: dict[str, str]) -> IntegrityError | None:
    """Insert `rows` in one rolled-back transaction; the error the last one raised."""
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            ids = {
                key: await conn.scalar(
                    text(
                        f"INSERT INTO {table} (name{cols}) VALUES ('{uuid.uuid4().hex}'{vals}) "
                        "RETURNING id"
                    )
                )
                for key, table, cols, vals in (
                    ("category_id", "categories", ", slug", f", 'c-{uuid.uuid4().hex[:12]}'"),
                    ("material_id", "materials", "", ""),
                    ("colour_id", "colours", "", ""),
                )
            }
            for row in rows[:-1]:
                await conn.execute(text(_insert_sql(row)), ids)
            try:
                await conn.execute(text(_insert_sql(rows[-1])), ids)
            except IntegrityError as exc:
                return exc
            return None
        finally:
            await transaction.rollback()


@pytest.mark.integration
async def test_valid_rows_of_both_types_are_accepted(db_engine: AsyncEngine) -> None:
    assert await _refusal(db_engine, _stl()) is None
    assert await _refusal(db_engine, _physical() | PHYSICAL_ONLY) is None


@pytest.mark.integration
@pytest.mark.parametrize("column", list(PHYSICAL_ONLY))
async def test_an_stl_row_cannot_carry_any_physical_only_field(
    db_engine: AsyncEngine, column: str
) -> None:
    """Done-when: an STL product with a lead time (or any physical field) cannot be stored."""
    error = await _refusal(db_engine, _stl() | {column: PHYSICAL_ONLY[column]})
    assert error is not None, f"an STL row with {column} was stored"
    assert _constraint_name(error) == "ck_products_type_integrity"


@pytest.mark.integration
@pytest.mark.parametrize("column", PHYSICAL_REQUIRED)
async def test_a_physical_row_needs_every_production_field(
    db_engine: AsyncEngine, column: str
) -> None:
    row = _physical()
    del row[column]
    error = await _refusal(db_engine, row)
    assert error is not None
    assert _constraint_name(error) == "ck_products_type_integrity"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("overrides", "physical", "constraint"),
    [
        ({"name": "'   '"}, False, "ck_products_name_not_blank"),
        ({"slug": "'Not A Slug'"}, False, "ck_products_slug_format"),
        ({"price_cents": "-1"}, False, "ck_products_price_non_negative"),
        ({"currency": "'EUR'"}, False, "ck_products_currency_usd"),
        ({"average_rating": "5.01"}, False, "ck_products_rating_range"),
        ({"review_count": "-1"}, False, "ck_products_review_count_non_negative"),
        ({"wishlist_count": "-1"}, False, "ck_products_wishlist_count_non_negative"),
        ({"version": "0"}, False, "ck_products_version_positive"),
        ({"production_lead_time_days": "-1"}, True, "ck_products_lead_time_non_negative"),
        ({"batch_size": "0"}, True, "ck_products_batch_size_positive"),
        ({"max_quantity_per_line": "0"}, True, "ck_products_max_quantity_positive"),
        ({"weight_grams": "0"}, True, "ck_products_weight_positive"),
    ],
)
async def test_value_checks_refuse_bad_rows(
    db_engine: AsyncEngine, overrides: dict[str, str], physical: bool, constraint: str
) -> None:
    row = (_physical() if physical else _stl()) | overrides
    error = await _refusal(db_engine, row)
    assert error is not None, f"{overrides} was stored"
    assert _constraint_name(error) == constraint


@pytest.mark.integration
@pytest.mark.parametrize(
    "dimensions",
    [
        "[1, 2, 3]",
        "7",
        '{"length_mm": 1, "width_mm": 1}',
        '{"length_mm": 1, "width_mm": 1, "height_mm": 1, "depth_mm": 1}',
        '{"length_mm": 0, "width_mm": 1, "height_mm": 1}',
        '{"length_mm": 1.5, "width_mm": 1, "height_mm": 1}',
        '{"length_mm": "1", "width_mm": 1, "height_mm": 1}',
        '{"length_mm": null, "width_mm": 1, "height_mm": 1}',
    ],
)
async def test_dimensions_must_be_three_positive_integers(
    db_engine: AsyncEngine, dimensions: str
) -> None:
    """The domain reads exactly these keys back; any other shape would break reads."""
    error = await _refusal(db_engine, _physical() | {"dimensions": f"'{dimensions}'"})
    assert error is not None, f"{dimensions} was stored"
    assert _constraint_name(error) == "ck_products_dimensions_shape"


@pytest.mark.integration
async def test_a_deleted_product_may_keep_its_visibility(db_engine: AsyncEngine) -> None:
    """Visibility and deletion are separate concepts (entities doc, Product)."""
    row = _stl() | {"is_visible": "true", "deleted_at": "now()"}
    assert await _refusal(db_engine, row) is None


@pytest.mark.integration
async def test_a_zero_day_lead_time_is_allowed(db_engine: AsyncEngine) -> None:
    assert await _refusal(db_engine, _physical() | {"production_lead_time_days": "0"}) is None


@pytest.mark.integration
async def test_live_slugs_are_unique_and_a_deleted_row_releases_its_slug(
    db_engine: AsyncEngine,
) -> None:
    first = _stl()
    second = _stl() | {"slug": first["slug"]}
    error = await _refusal(db_engine, first, second)
    assert error is not None
    assert _constraint_name(error) == "ix_products_live_slug"
    deleted = first | {"deleted_at": "now()"}
    assert await _refusal(db_engine, deleted, second) is None


@pytest.mark.integration
@pytest.mark.parametrize("table", ["categories", "materials", "colours"])
async def test_reference_foreign_keys_are_on_delete_restrict(
    db_engine: AsyncEngine, table: str
) -> None:
    """`ON DELETE RESTRICT` (database-design.md 6.4)."""
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT confdeltype::text FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = 'products'::regclass AND confrelid = CAST(:t AS regclass)"
            ),
            {"t": table},
        )
        assert [row[0] for row in rows] == ["r"]


@pytest.mark.integration
async def test_the_search_vector_weights_name_above_description(db_engine: AsyncEngine) -> None:
    """Generated and stored, `english` config: name lexemes are A, description B."""
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            category_id = await conn.scalar(
                text("INSERT INTO categories (name, slug) VALUES ('c', :s) RETURNING id"),
                {"s": f"c-{uuid.uuid4().hex[:12]}"},
            )
            vector = await conn.scalar(
                text(
                    "INSERT INTO products "
                    "(type, category_id, name, slug, price_cents, description) "
                    "VALUES ('stl', :c, 'Dragons', :s, 1, 'Printed lamps') "
                    "RETURNING search_vector::text"
                ),
                {"c": category_id, "s": f"p-{uuid.uuid4().hex[:12]}"},
            )
        finally:
            await transaction.rollback()
    assert "'dragon':1A" in vector
    assert "'lamp':3B" in vector
