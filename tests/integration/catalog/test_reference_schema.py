"""The three reference tables as the frozen design specifies them.

Read from PostgreSQL's own catalogue rather than from ORM metadata, because the
question is what the *migration* built - metadata would happily agree with
itself while the migrated database differed.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

LIFECYCLE_COLUMNS = {"id", "name", "is_active", "deleted_at", "created_at", "updated_at"}


@pytest.mark.integration
async def test_categories_match_the_frozen_design(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name = 'categories'"
                )
            )
        ).all()

    columns = {row[0]: (row[1], row[2]) for row in rows}

    assert set(columns) == LIFECYCLE_COLUMNS | {"slug"}
    assert columns["name"] == ("text", "NO")
    assert columns["slug"] == ("text", "NO")
    assert columns["is_active"] == ("boolean", "NO")
    assert columns["deleted_at"] == ("timestamp with time zone", "YES")
    assert columns["created_at"] == ("timestamp with time zone", "NO")
    assert columns["updated_at"] == ("timestamp with time zone", "NO")


@pytest.mark.integration
async def test_categories_have_no_hierarchy_column(db_engine: AsyncEngine) -> None:
    """V1 has no subcategories. `parent_id` is the likely accident."""
    async with db_engine.connect() as conn:
        names = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'categories'"
                    )
                )
            ).all()
        }
    assert "parent_id" not in names


@pytest.mark.integration
@pytest.mark.parametrize("table", ["materials", "colours"])
async def test_simple_reference_tables_match_the_frozen_design(
    db_engine: AsyncEngine, table: str
) -> None:
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name = :t"
                ),
                {"t": table},
            )
        ).all()

    columns = {row[0]: (row[1], row[2]) for row in rows}

    # No slug: materials and colours are never addressed by URL.
    assert set(columns) == LIFECYCLE_COLUMNS
    assert "slug" not in columns
    assert columns["name"] == ("text", "NO")
    assert columns["deleted_at"] == ("timestamp with time zone", "YES")


@pytest.mark.integration
async def test_the_live_slug_index_exists_and_is_partial(db_engine: AsyncEngine) -> None:
    """The whole slug contract in one object: unique, on `slug`, and partial on
    `deleted_at IS NULL` so archiving releases the value."""
    async with db_engine.connect() as conn:
        definition = await conn.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'categories' AND indexname = 'ix_categories_live_slug'"
            )
        )

    assert definition is not None, "ix_categories_live_slug is missing"
    assert "UNIQUE" in definition
    assert "(slug)" in definition
    assert "deleted_at IS NULL" in definition


def _constraint_name(error: IntegrityError) -> str | None:
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


async def _insert_twice(db_engine: AsyncEngine, first: str, second: str) -> IntegrityError | None:
    """Run two INSERTs in one transaction that is always rolled back; return the
    error the second one raised, if any."""
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text(first))
            try:
                await conn.execute(text(second))
            except IntegrityError as exc:
                return exc
            return None
        finally:
            await transaction.rollback()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("table", "column", "index"),
    [
        ("materials", "name", "ix_materials_live_name_ci"),
        ("colours", "name", "ix_colours_live_name_ci"),
        ("categories", "slug", "ix_categories_live_slug_ci"),
    ],
)
async def test_the_case_insensitive_live_index_exists_and_is_partial(
    db_engine: AsyncEngine, table: str, column: str, index: str
) -> None:
    async with db_engine.connect() as conn:
        definition = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = :t AND indexname = :i"),
            {"t": table, "i": index},
        )
    assert definition is not None, f"{index} is missing"
    assert "UNIQUE" in definition
    assert f"(lower({column}))" in definition
    assert "deleted_at IS NULL" in definition


@pytest.mark.integration
@pytest.mark.parametrize(
    ("table", "index"),
    [("materials", "ix_materials_live_name_ci"), ("colours", "ix_colours_live_name_ci")],
)
async def test_live_names_are_unique_ignoring_case(
    db_engine: AsyncEngine, table: str, index: str
) -> None:
    """Q-1: "PLA" beside "pla" would be two facet values for one material.
    Enforced by the database, so no writer - API, SQL, importer - can add one."""
    name = f"Pla-{uuid.uuid4().hex[:8]}"
    error = await _insert_twice(
        db_engine,
        f"INSERT INTO {table} (name) VALUES ('{name}')",
        f"INSERT INTO {table} (name) VALUES ('{name.upper()}')",
    )
    assert error is not None, "a live case-variant name was accepted"
    assert _constraint_name(error) == index


@pytest.mark.integration
@pytest.mark.parametrize("table", ["materials", "colours"])
async def test_an_archived_name_does_not_block_a_live_one(
    db_engine: AsyncEngine, table: str
) -> None:
    """The index is partial, so archiving releases a name - as for slugs."""
    name = f"Pla-{uuid.uuid4().hex[:8]}"
    error = await _insert_twice(
        db_engine,
        f"INSERT INTO {table} (name, is_active, deleted_at) VALUES ('{name}', false, now())",
        f"INSERT INTO {table} (name) VALUES ('{name.lower()}')",
    )
    assert error is None, f"an archived name blocked a live one: {error}"


@pytest.mark.integration
async def test_category_slugs_are_unique_ignoring_case(db_engine: AsyncEngine) -> None:
    """The application lowercases slugs; this is the guarantee for any other
    writer. Only the case-insensitive index can refuse this pair - the exact
    one sees two different strings."""
    slug = f"lamps-{uuid.uuid4().hex[:8]}"
    error = await _insert_twice(
        db_engine,
        f"INSERT INTO categories (name, slug) VALUES ('A', '{slug}')",
        f"INSERT INTO categories (name, slug) VALUES ('B', '{slug.upper()}')",
    )
    assert error is not None, "a live case-variant slug was accepted"
    assert _constraint_name(error) == "ix_categories_live_slug_ci"


@pytest.mark.integration
@pytest.mark.parametrize("table", ["categories", "materials", "colours"])
async def test_an_archived_row_cannot_be_active(db_engine: AsyncEngine, table: str) -> None:
    """A-13: `archive()` clears `is_active`; the CHECK makes the database refuse
    the contradictory row from any writer."""
    columns = "name, slug" if table == "categories" else "name"
    values = f"'x', 'arch-{uuid.uuid4().hex[:8]}'" if table == "categories" else "'x'"
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            with pytest.raises(IntegrityError) as raised:
                await conn.execute(
                    text(
                        f"INSERT INTO {table} ({columns}, is_active, deleted_at) "
                        f"VALUES ({values}, true, now())"
                    )
                )
        finally:
            await transaction.rollback()
    assert _constraint_name(raised.value) == f"ck_{table}_archived_not_active"


@pytest.mark.integration
async def test_the_reference_tables_have_no_outgoing_foreign_keys(db_engine: AsyncEngine) -> None:
    """The reference tables reference nothing; since VS-013, `products` points at
    them (test_product_schema.py), never the other way round."""
    async with db_engine.connect() as conn:
        count = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid IN ('categories'::regclass, 'materials'::regclass, "
                "'colours'::regclass)"
            )
        )
    assert count == 0
