"""Migration `b7e4c1d9a2f6` against rows that already exist.

It adds a case-insensitive live-name/slug unique index and an
archived-not-active CHECK to tables that may already hold data, so both of its
existing-row paths are exercised on a throwaway PostgreSQL:

- archived rows still flagged active are normalised, so the CHECK can be added;
- live case-duplicates stop the upgrade *before* anything changes, naming each
  group, because choosing which duplicate survives is an administrator's call.
"""

import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

BEFORE = "5e1c0a7d2b94"
REVISION = "b7e4c1d9a2f6"


async def _execute(url: str, statements: list[str]) -> list[Any]:
    engine = create_async_engine(url)
    results = []
    async with engine.begin() as connection:
        for statement in statements:
            result = await connection.execute(text(statement))
            results.append(result.all() if result.returns_rows else None)
    await engine.dispose()
    return results


def _current(url: str) -> str:
    [[(version,)]] = asyncio.run(_execute(url, ["SELECT version_num FROM alembic_version"]))
    return str(version)


@pytest.mark.integration
def test_existing_rows_are_normalised_or_the_upgrade_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config("alembic.ini")
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            command.upgrade(config, BEFORE)
            asyncio.run(
                _execute(
                    url,
                    [
                        # Contradictory rows the CHECK would reject.
                        "INSERT INTO materials (name, is_active, deleted_at) "
                        "VALUES ('Stale', true, now())",
                        "INSERT INTO categories (name, slug, is_active, deleted_at) "
                        "VALUES ('Old', 'old', true, now())",
                        # An archived case twin is not a duplicate: only live rows count.
                        "INSERT INTO colours (name) VALUES ('Red')",
                        "INSERT INTO colours (name, is_active, deleted_at) "
                        "VALUES ('red', false, now())",
                        # Live case duplicates the index would reject.
                        "INSERT INTO materials (name) VALUES ('PLA'), ('pla')",
                    ],
                )
            )

            with pytest.raises(Exception, match="differ only by case") as refused:
                command.upgrade(config, REVISION)
            assert "materials.name 'pla' x2" in str(refused.value)
            assert "colours" not in str(refused.value), "an archived twin is not a duplicate"
            assert _current(url) == BEFORE, "a refused upgrade must change nothing"

            # The administrator resolves it by archiving one of the pair.
            asyncio.run(
                _execute(
                    url,
                    [
                        "UPDATE materials SET deleted_at = now(), is_active = false "
                        "WHERE name = 'pla'"
                    ],
                )
            )
            command.upgrade(config, REVISION)
            assert _current(url) == REVISION

            [materials, categories] = asyncio.run(
                _execute(
                    url,
                    [
                        "SELECT name, is_active FROM materials WHERE deleted_at IS NOT NULL",
                        "SELECT slug, is_active FROM categories",
                    ],
                )
            )
            assert set(materials) == {("Stale", False), ("pla", False)}
            assert categories == [("old", False)]

            command.downgrade(config, BEFORE)
            command.upgrade(config, REVISION)
            assert _current(url) == REVISION
        finally:
            get_settings.cache_clear()
