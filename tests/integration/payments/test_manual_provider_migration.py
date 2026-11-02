"""Migration 941b40d285ce (VS-050) on its own throwaway Postgres: stepping back drops the
CHECK, the index and the hold setting but keeps the enum value (PostgreSQL cannot drop
one); stepping forward again restores them. The cap migration steps the same way."""

import asyncio
import os
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

REVISION = "941b40d285ce"
CAP_REVISION = "95ffee5fde3b"
_STATE = """
SELECT
 (SELECT count(*) FROM pg_constraint WHERE conname = 'ck_payments_manual_never_processing')
   AS checks,
 (SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_payments_awaiting_manual') AS indexes,
 (SELECT value::text FROM settings WHERE key = 'manual_payment_hold_period') AS hold,
 (SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'payment_provider' AND e.enumlabel = 'manual') AS enum_values
"""


async def _state(url: str) -> Any:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        row = (await conn.execute(text(_STATE))).one()
    await engine.dispose()
    return tuple(row)


async def _cap(url: str) -> Any:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT value::text FROM settings WHERE key = 'manual_max_open_orders'")
        )
    await engine.dispose()
    return value


@pytest.mark.integration
def test_stepping_back_and_forward_restores_the_manual_provider_schema() -> None:
    previous = os.environ.get("DATABASE_URL")
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            url = postgres.get_connection_url()
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            config = Config("alembic.ini")
            command.upgrade(config, "head")
            assert asyncio.run(_state(url)) == (1, 1, "604800", 1)
            command.downgrade(config, f"{REVISION}-1")
            assert asyncio.run(_state(url)) == (0, 0, None, 1)
            command.upgrade(config, REVISION)
            assert asyncio.run(_state(url)) == (1, 1, "604800", 1)
            command.upgrade(config, CAP_REVISION)  # the audit's open-order cap (Q-1)
            assert asyncio.run(_cap(url)) == "3"
            command.downgrade(config, REVISION)
            assert asyncio.run(_cap(url)) is None
            command.upgrade(config, "head")
            assert asyncio.run(_cap(url)) == "3"
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
