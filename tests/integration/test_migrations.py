import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

EXPECTED_EXTENSIONS = {"pgcrypto", "citext", "pg_trgm", "unaccent", "btree_gin"}


@pytest.mark.integration
def test_baseline_migration_creates_required_extensions() -> None:
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        os.environ["DATABASE_URL"] = postgres.get_connection_url()
        get_settings.cache_clear()

        command.upgrade(Config("alembic.ini"), "head")

        async def fetch_extension_names() -> set[str]:
            engine = create_async_engine(postgres.get_connection_url())
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT extname FROM pg_extension"))
                names = {row[0] for row in result}
            await engine.dispose()
            return names

        installed = asyncio.run(fetch_extension_names())
        assert EXPECTED_EXTENSIONS.issubset(installed)

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
