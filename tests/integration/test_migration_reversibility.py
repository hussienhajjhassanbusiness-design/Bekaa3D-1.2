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
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

CART_REVISION = "bde6135b2538"
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

        # VS-022: one head, with the cart migration in its chain (later migrations need no
        # edit here). Stepping back over it drops cart_items before the products unique
        # key its composite FK needs.
        scripts = ScriptDirectory.from_config(config)
        assert len(scripts.get_heads()) == 1, scripts.get_heads()
        chain = {script.revision: script for script in scripts.walk_revisions()}
        assert CART_REVISION in chain
        assert chain[CART_REVISION].down_revision == "75ad58ebd9e5"
        cart_tables = {"carts", "cart_items"}
        id_type_key = "SELECT conname FROM pg_constraint WHERE conname = 'uq_products_id_type'"
        assert cart_tables <= asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(id_type_key)) == {"uq_products_id_type"}
        command.downgrade(config, f"{CART_REVISION}-1")
        assert cart_tables.isdisjoint(asyncio.run(fetch(table_query)))
        assert asyncio.run(fetch(id_type_key)) == set()
        assert "product_type" in asyncio.run(fetch(enum_query)), "products still owns it"
        command.upgrade(config, "head")
        assert cart_tables <= asyncio.run(fetch(table_query))

        # VS-046: stepping back over 75ad58ebd9e5 drops its table and its two settings.
        retention_keys = (
            "SELECT key FROM settings WHERE key IN "
            "('security_token_retention_period', 'session_retention_period')"
        )
        assert len(asyncio.run(fetch(retention_keys))) == 2
        command.downgrade(config, "75ad58ebd9e5-1")
        assert "ip_hash_salts" not in asyncio.run(fetch(table_query))
        assert asyncio.run(fetch(retention_keys)) == set()
        command.upgrade(config, "head")

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
        assert "ip_hash_salts" not in leftover_tables
        assert "cart_items" not in leftover_tables

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
