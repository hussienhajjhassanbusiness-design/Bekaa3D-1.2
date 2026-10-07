"""VS-012a: `audit_logs` becomes a monthly range-partitioned table (ADR-015).

The migration tests run against their own throwaway PostgreSQL so they can walk
the chain to the revision before this one, seed rows into the *plain* table, and
then go up, down and up again without disturbing the shared test database. The
remaining tests use the shared, fully migrated schema.
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from app.jobs.partitions import add_months, first_of_month
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import client_for, create_user, login

PREVIOUS = "b7e4c1d9a2f6"
THIS = "c3d5e7f9a1b2"
USER_ID = "22222222-2222-2222-2222-222222222222"

# Three different months, including both sides of a month boundary in UTC.
SEED_ROWS = [
    ("11111111-0000-0000-0000-000000000001", "2026-07-15 12:00:00+00"),
    ("11111111-0000-0000-0000-000000000002", "2026-08-31 23:59:59.999999+00"),
    ("11111111-0000-0000-0000-000000000003", "2026-09-01 00:00:00+00"),
    ("11111111-0000-0000-0000-000000000004", "2026-09-20 08:00:00+00"),
]


async def _run(url: str, statements: list[str]) -> list[Any]:
    engine = create_async_engine(url)
    out: list[Any] = []
    async with engine.begin() as conn:
        for statement in statements:
            result = await conn.execute(text(statement))
            out.append(result.all() if result.returns_rows else None)
    await engine.dispose()
    return out


def _q(url: str, statement: str) -> list[Any]:
    [rows] = asyncio.run(_run(url, [statement]))
    return list(rows)


@pytest.fixture
def fresh_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, Config]]:
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            yield url, Config("alembic.ini")
        finally:
            get_settings.cache_clear()


def _schema(url: str) -> dict[str, Any]:
    return {
        "partitioned": _q(
            url,
            "SELECT c.relkind::text FROM pg_class c WHERE c.relname = 'audit_logs'",
        )[0][0],
        "pk": _q(
            url,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'audit_logs'::regclass AND contype = 'p'",
        )[0][0],
        "constraints": sorted(
            r[0]
            for r in _q(
                url, "SELECT conname FROM pg_constraint WHERE conrelid = 'audit_logs'::regclass"
            )
        ),
        "indexes": sorted(
            r[0]
            for r in _q(
                url,
                "SELECT indexname || ' ' || indexdef FROM pg_indexes "
                "WHERE tablename = 'audit_logs'",
            )
        ),
        "default": _q(
            url,
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'audit_logs' AND column_name = 'created_at'",
        )[0][0],
    }


@pytest.mark.integration
def test_upgrade_down_and_up_again_keeps_every_row_and_restores_the_original_table(
    fresh_db: tuple[str, Config],
) -> None:
    url, config = fresh_db
    command.upgrade(config, PREVIOUS)
    original = _schema(url)
    asyncio.run(
        _run(
            url,
            [
                f"INSERT INTO users (id, email, password_hash) "
                f"VALUES ('{USER_ID}', 'seed@example.com', 'x')",
                *(
                    f"INSERT INTO audit_logs (id, actor_user_id, action, entity_type, created_at) "
                    f"VALUES ('{rid}', '{USER_ID}', 'seed', 'User', '{ts}')"
                    for rid, ts in SEED_ROWS
                ),
            ],
        )
    )
    before = sorted(_q(url, "SELECT id::text, created_at FROM audit_logs"))

    command.upgrade(config, THIS)
    after = sorted(_q(url, "SELECT id::text, created_at FROM audit_logs"))
    assert after == before, "every row and timestamp survives the conversion"
    schema = _schema(url)
    assert schema["partitioned"] == "p"
    assert schema["pk"] == "PRIMARY KEY (id, created_at)"
    assert "clock_timestamp()" in schema["default"]
    assert not _q(url, "SELECT 1 FROM pg_class WHERE relname = 'audit_logs_legacy'")
    partitions = sorted(
        r[0]
        for r in _q(
            url,
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = 'audit_logs'::regclass",
        )
    )
    current = first_of_month(datetime.now(UTC))
    expected_last = add_months(current, 3)
    assert partitions[0] == "audit_logs_y2026m07"
    assert partitions[-1] == f"audit_logs_y{expected_last.year:04d}m{expected_last.month:02d}"
    assert not _q(
        url,
        "SELECT 1 FROM pg_partitioned_table p JOIN pg_class c ON c.oid = p.partdefid "
        "WHERE p.partrelid = 'audit_logs'::regclass",
    ), "there must be no DEFAULT partition"
    # Each seeded row sits in its own month's partition.
    placed = dict(_q(url, "SELECT id::text, tableoid::regclass::text FROM audit_logs"))
    assert placed[SEED_ROWS[1][0]] == "audit_logs_y2026m08"
    assert placed[SEED_ROWS[2][0]] == "audit_logs_y2026m09"
    # The FK still sets the actor to NULL when the user goes.
    asyncio.run(_run(url, [f"DELETE FROM users WHERE id = '{USER_ID}'"]))
    assert _q(url, "SELECT count(*) FROM audit_logs WHERE actor_user_id IS NOT NULL") == [(0,)]
    assert len(_q(url, "SELECT 1 FROM audit_logs")) == len(SEED_ROWS)

    command.downgrade(config, PREVIOUS)
    assert sorted(_q(url, "SELECT id::text, created_at FROM audit_logs")) == before
    assert _schema(url) == original, "downgrade restores the original table, names and indexes"
    assert not _q(url, "SELECT 1 FROM pg_class WHERE relname LIKE 'audit_logs_y%'")

    command.upgrade(config, THIS)
    assert sorted(_q(url, "SELECT id::text, created_at FROM audit_logs")) == before
    assert _schema(url) == schema


@pytest.mark.integration
def test_upgrading_an_empty_table_starts_at_the_current_month(
    fresh_db: tuple[str, Config],
) -> None:
    url, config = fresh_db
    command.upgrade(config, THIS)
    current = first_of_month(datetime.now(UTC))
    names = sorted(
        r[0]
        for r in _q(
            url,
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = 'audit_logs'::regclass",
        )
    )
    expected = [
        f"audit_logs_y{m.year:04d}m{m.month:02d}"
        for m in (add_months(current, n) for n in range(4))
    ]
    assert names == expected


# --------------------------------------------------------------------------
# Against the shared, migrated schema
# --------------------------------------------------------------------------


@pytest.mark.integration
async def test_an_insert_lands_in_its_months_partition(db_session: AsyncSession) -> None:
    row = AuditLogModel(action="test.partition", entity_type="Test")
    db_session.add(row)
    await db_session.flush()
    # RETURNING gave the ORM the server-default created_at: the identity is complete.
    assert row.created_at is not None
    month = first_of_month(row.created_at)
    placed = await db_session.scalar(
        text("SELECT tableoid::regclass::text FROM audit_logs WHERE id = :id"), {"id": row.id}
    )
    await db_session.rollback()
    assert placed == f"audit_logs_y{month.year:04d}m{month.month:02d}"


@pytest.mark.integration
async def test_an_insert_outside_every_partition_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="no partition"):
        await db_session.execute(
            text(
                "INSERT INTO audit_logs (action, entity_type, created_at) "
                "VALUES ('test.outside', 'Test', '1999-01-01 00:00:00+00')"
            )
        )
    await db_session.rollback()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_existing_audit_writes_still_work_end_to_end(db_session: AsyncSession) -> None:
    """A login writes `user.logged_in` through the normal unit of work."""
    user = await create_user(db_session)
    user_id, email = user.id, user.email
    with client_for(main_app) as client:
        login(client, email)
    db_session.expire_all()
    rows = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.actor_user_id == user_id,
                AuditLogModel.action == "user.logged_in",
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].id is not None and isinstance(rows[0].id, uuid.UUID)


@pytest.mark.integration
async def test_the_shared_test_schema_is_partitioned(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        kind = await conn.scalar(
            text("SELECT relkind::text FROM pg_class WHERE relname = 'audit_logs'")
        )
    assert kind == "p"
