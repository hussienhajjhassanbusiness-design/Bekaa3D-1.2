"""The `notifications` table as the frozen design specifies it.

Read from PostgreSQL's own catalogue rather than from the ORM metadata, because
the question is what the *migration* built - metadata would happily agree with
itself while the migrated database differed.

Deliberately no EXPLAIN assertions. On a table with a handful of test rows
PostgreSQL may legitimately prefer a sequential scan over either index, so a
test that demanded an index scan would be asserting the planner's cost model
rather than the schema, and would fail for reasons that are not defects.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DOCUMENTED_TYPES = ["account", "order", "payment", "refund", "offer", "download"]


@pytest.mark.integration
async def test_the_columns_match_the_frozen_design(db_engine: AsyncEngine) -> None:
    """database-design.md 12.3 - six columns, and the nullability that makes
    `read_at IS NULL` mean unread."""
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name = 'notifications' "
                    "ORDER BY column_name"
                )
            )
        ).all()

    columns = {row[0]: (row[1], row[2]) for row in rows}

    assert set(columns) == {"id", "user_id", "type", "payload", "read_at", "created_at"}
    assert columns["id"][1] == "NO"
    assert columns["user_id"][1] == "NO"
    assert columns["type"][1] == "NO"
    assert columns["payload"] == ("jsonb", "NO")
    # The one nullable column, and the entire read/unread model.
    assert columns["read_at"] == ("timestamp with time zone", "YES")
    assert columns["created_at"] == ("timestamp with time zone", "NO")


@pytest.mark.integration
async def test_the_table_has_no_columns_the_design_does_not_define(
    db_engine: AsyncEngine,
) -> None:
    """Stated from the other direction. `updated_at` is the likely accident -
    every other table in this schema has one - and `deleted_at` would quietly
    imply a retention decision that has not been made."""
    async with db_engine.connect() as conn:
        names = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'notifications'"
                    )
                )
            ).all()
        }

    assert "updated_at" not in names
    assert "deleted_at" not in names


@pytest.mark.integration
async def test_the_notification_type_enum_holds_exactly_the_six_categories(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        values = [
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'notification_type' ORDER BY e.enumsortorder"
                    )
                )
            ).all()
        ]

    assert values == DOCUMENTED_TYPES


@pytest.mark.integration
async def test_both_documented_indexes_exist_with_the_right_shape(
    db_engine: AsyncEngine,
) -> None:
    """`(user_id, created_at DESC)` and the same again partial on unread.

    Asserted on the index definition text, which is how the DESC ordering and
    the partial predicate are actually visible.
    """
    async with db_engine.connect() as conn:
        definitions = {
            row[0]: row[1]
            for row in (
                await conn.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE tablename = 'notifications'"
                    )
                )
            ).all()
        }

    recent = definitions.get("ix_notifications_user_recent")
    unread = definitions.get("ix_notifications_user_unread")

    assert recent is not None, f"missing; have {sorted(definitions)}"
    assert "user_id" in recent
    assert "created_at DESC" in recent
    assert "WHERE" not in recent, "the recent index must cover read and unread alike"

    assert unread is not None, f"missing; have {sorted(definitions)}"
    assert "user_id" in unread
    assert "created_at DESC" in unread
    # The partial predicate is the whole point: this index is exactly the
    # unread working set, which is what makes the unread badge cheap.
    assert "read_at IS NULL" in unread


@pytest.mark.integration
async def test_the_foreign_key_cascades(db_engine: AsyncEngine) -> None:
    """Asserted at the schema level as well as behaviourally (see
    test_notification_writer), because this is the constraint that decides
    whether the unverified-account purge job can run at all."""
    async with db_engine.connect() as conn:
        rule = await conn.scalar(
            text(
                # Cast to text: `confdeltype` is PostgreSQL's internal "char"
                # type, which asyncpg hands back as bytes rather than str.
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = 'notifications'::regclass AND contype = 'f'"
            )
        )

    # 'c' = CASCADE, 'n' = SET NULL, 'a' = NO ACTION.
    assert rule == "c"
