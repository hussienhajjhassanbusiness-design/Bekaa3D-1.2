"""Migration 089f97a72014 (VS-049) on its own throwaway Postgres: stepping back drops the
columns, and stepping forward again gives every existing physical product and line
`online_or_cash` and every STL row nothing, which today's behaviour needs."""

import asyncio
import os
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from tests.integration.fulfillment.order_support import seed_physical_order

REVISION = "089f97a72014"
_VALUES = """
SELECT
 (SELECT array_agg(DISTINCT type::text || ':' || coalesce(accepted_payment_methods::text, '-'))
    FROM products) AS products,
 (SELECT array_agg(DISTINCT product_type::text || ':'
    || coalesce(accepted_payment_methods_snapshot::text, '-')) FROM order_items) AS lines
"""
_COLUMNS = """
SELECT count(*) FROM information_schema.columns
WHERE column_name IN ('accepted_payment_methods', 'accepted_payment_methods_snapshot')
"""


async def _seed(url: str) -> None:
    """A cash order and an online order with an STL line: both types on both tables."""
    engine = create_async_engine(url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await seed_physical_order(db)
        await seed_physical_order(
            db, payment_method="online", payment_status="paid", stl_line="awaiting_delivery"
        )
    await engine.dispose()


async def _row(url: str, sql: str) -> Any:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql))).one()
    await engine.dispose()
    return row


@pytest.mark.integration
def test_stepping_back_and_forward_backfills_existing_rows() -> None:
    previous = os.environ.get("DATABASE_URL")
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            url = postgres.get_connection_url()
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            config = Config("alembic.ini")
            command.upgrade(config, "head")
            asyncio.run(_seed(url))

            command.downgrade(config, f"{REVISION}-1")
            assert asyncio.run(_row(url, _COLUMNS))[0] == 0
            command.upgrade(config, REVISION)
            products, lines = asyncio.run(_row(url, _VALUES))
            assert sorted(products) == ["physical:online_or_cash", "stl:-"]
            assert sorted(lines) == ["physical:online_or_cash", "stl:-"]
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
