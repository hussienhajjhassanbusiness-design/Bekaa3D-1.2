"""Full-chain migration reversibility (B01).

`alembic downgrade -1` then `upgrade head` - the check CONTRIBUTING.md asks for
before merging a migration PR - would not have caught B01: it only steps back
over the newest revision, and the migrations that create enum types sit further
down the chain. Only a walk to `base` and back exercises them, which is what
SRS 24.7 means by "migration reversibility check".
"""

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

EXPECTED_ENUMS = {"user_role", "outbox_status", "setting_type", "notification_type"}


@pytest.mark.integration
def test_full_downgrade_and_upgrade_round_trips() -> None:
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        config = Config("alembic.ini")

        async def fetch(query: str) -> set[str]:
            engine = create_async_engine(url)
            async with engine.connect() as conn:
                result = await conn.execute(text(query))
                names = {row[0] for row in result}
            await engine.dispose()
            return names

        enum_query = "SELECT typname FROM pg_type WHERE typtype = 'e'"
        table_query = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"

        command.upgrade(config, "head")
        assert asyncio.run(fetch(enum_query)) >= EXPECTED_ENUMS

        command.downgrade(config, "base")

        # The actual defect: tables went, the enum types stayed, and the next
        # CREATE TYPE then failed with DuplicateObjectError.
        leftover_enums = asyncio.run(fetch(enum_query))
        assert EXPECTED_ENUMS.isdisjoint(leftover_enums), (
            f"enum types survived downgrade: {sorted(EXPECTED_ENUMS & leftover_enums)}"
        )
        leftover_tables = asyncio.run(fetch(table_query))
        assert "users" not in leftover_tables
        assert "email_outbox" not in leftover_tables

        # This is the call that used to raise.
        command.upgrade(config, "head")
        assert asyncio.run(fetch(enum_query)) >= EXPECTED_ENUMS

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()


@pytest.mark.integration
async def test_schema_matches_the_frozen_design(db_engine: AsyncEngine) -> None:
    """F06/F07 - two objects database-design.md specifies that the VS-002
    migration omitted.

    Uses the migrated `db_engine` fixture directly rather than rebuilding an
    engine from DATABASE_URL: other modules in the suite reassign that variable,
    so reading it here made the test depend on execution order.
    """
    async with db_engine.connect() as conn:
        # database-design.md 13.3: attempt_count CHECK >= 0
        checks = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conrelid = 'email_outbox'::regclass AND contype = 'c' "
                "AND conname = 'ck_email_outbox_attempt_count_non_negative'"
            )
        )
        # database-design.md 19.11: verification_tokens(expires_at) for the purge
        indexes = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_indexes WHERE tablename = 'verification_tokens' "
                "AND indexname = 'ix_verification_tokens_expires_at_live'"
            )
        )

    assert checks == 1
    assert indexes == 1
