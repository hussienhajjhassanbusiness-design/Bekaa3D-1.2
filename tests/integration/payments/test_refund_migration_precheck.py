"""VS-030 PR A's Q-1 precheck (plan 4.2a step 2) on its own throwaway Postgres: a line whose
`user_id` differs from its order's makes the migration refuse, name order ids only, and
leave nothing behind; fixed by hand, the same upgrade then succeeds."""

import asyncio
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from tests.integration.deep_support import create_user
from tests.integration.fulfillment.order_support import seed_physical_order

REFUNDS_REVISION = "c01e53ab3e0f"
_STATE = """
SELECT
 (SELECT version_num FROM alembic_version) AS version,
 (SELECT count(*) FROM pg_tables WHERE tablename IN
    ('refunds', 'refund_items', 'chargebacks', 'chargeback_items')) AS tables,
 (SELECT count(*) FROM pg_type WHERE typname IN ('refund_kind', 'refund_status')) AS types,
 (SELECT count(*) FROM pg_constraint WHERE conname IN ('uq_orders_id_user',
    'uq_order_items_id_order', 'uq_payments_id_order_provider',
    'fk_order_items_order_owner')) AS keys
"""


async def _seed_mismatch(url: str) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    """(order id, line id, the buyer's and the stranger's emails); one line re-owned."""
    engine = create_async_engine(url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        order = await seed_physical_order(db, line_states=["pending", "pending"])
        buyer = await db.scalar(text("SELECT email FROM users WHERE id = :u"), {"u": order.user_id})
        stranger = await create_user(db)
        await db.execute(
            text("UPDATE order_items SET user_id = :s WHERE id = :i"),
            {"s": stranger.id, "i": order.line_ids[0]},
        )
        await db.commit()
        result = (order.order_id, order.line_ids[0], str(buyer), stranger.email)
    await engine.dispose()
    return result


async def _state(url: str) -> tuple[str, int, int, int]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        row = (await conn.execute(text(_STATE))).one()
    await engine.dispose()
    return row.version, row.tables, row.types, row.keys


async def _give_back(url: str, line_id: uuid.UUID) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE order_items i SET user_id = o.user_id FROM orders o"
                " WHERE o.id = i.order_id AND i.id = :i"
            ),
            {"i": line_id},
        )
    await engine.dispose()


@pytest.mark.integration
def test_mismatched_lines_refuse_the_migration_and_nothing_is_created() -> None:
    previous = os.environ.get("DATABASE_URL")
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            url = postgres.get_connection_url()
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            config = Config("alembic.ini")
            parent = ScriptDirectory.from_config(config).get_revision(REFUNDS_REVISION)
            assert parent is not None and isinstance(parent.down_revision, str)
            command.upgrade(config, parent.down_revision)
            order_id, line_id, buyer, stranger = asyncio.run(_seed_mismatch(url))

            with pytest.raises(RuntimeError) as refused:
                command.upgrade(config, "head")
            message = str(refused.value)
            assert message.startswith("fk_order_items_order_owner: 1 order(s)"), message
            assert str(order_id) in message
            assert str(line_id) not in message and buyer not in message
            assert stranger not in message
            # One transaction: the enum types, keys and tables were all rolled back.
            assert asyncio.run(_state(url)) == (parent.down_revision, 0, 0, 0)

            asyncio.run(_give_back(url, line_id))
            command.upgrade(config, "head")
            version, tables, types, keys = asyncio.run(_state(url))
            assert (tables, types, keys) == (4, 2, 4) and version != parent.down_revision
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
