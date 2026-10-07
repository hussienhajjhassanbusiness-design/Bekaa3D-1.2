"""VS-012a: the `ensure_partitions` job (ADR-015, SRS 23).

Runs against the shared migrated schema. Tests that need the job to actually
*create* something pass a `now` far in the future, so they never collide with
the partitions the migration made for the present; the extra empty partitions
they leave behind are harmless.
"""

import asyncio
import io
import logging
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.logging import configure_logging
from app.jobs import partitions
from app.jobs.partitions import ensure_partitions, partition_name
from app.jobs.registry import CRON_JOBS, FUNCTIONS


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _partitions(engine: AsyncEngine) -> dict[str, str]:
    """name -> bound expression, for every audit_logs partition."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) "
                "FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = 'audit_logs'::regclass"
            )
        )
        return {str(name): str(bound) for name, bound in rows.all()}


async def _bounds_utc(engine: AsyncEngine, name: str) -> tuple[datetime, datetime]:
    async with engine.connect() as conn:
        await conn.execute(text("SET TIME ZONE 'UTC'"))
        bound = await conn.scalar(
            text("SELECT pg_get_expr(relpartbound, oid) FROM pg_class WHERE relname = :n"),
            {"n": name},
        )
    low, high = (part.split("'")[1] for part in bound.split(" TO "))
    return datetime.fromisoformat(low), datetime.fromisoformat(high)


@pytest.mark.integration
async def test_a_second_run_creates_nothing(db_engine: AsyncEngine) -> None:
    now = datetime(2041, 2, 10, tzinfo=UTC)
    first = await ensure_partitions(_ctx(db_engine), now=now)
    second = await ensure_partitions(_ctx(db_engine), now=now)
    existing = await _partitions(db_engine)
    assert first in (0, 4)  # 0 if an earlier run already made them
    assert second == 0
    for name in ("audit_logs_y2041m02", "audit_logs_y2041m05"):
        assert name in existing


@pytest.mark.integration
async def test_at_the_current_time_the_migration_already_covered_everything(
    db_engine: AsyncEngine,
) -> None:
    assert await ensure_partitions(_ctx(db_engine)) == 0


@pytest.mark.integration
async def test_two_concurrent_runs_neither_error_nor_duplicate(db_engine: AsyncEngine) -> None:
    now = datetime(2042, 6, 1, tzinfo=UTC)
    results = await asyncio.gather(
        ensure_partitions(_ctx(db_engine), now=now),
        ensure_partitions(_ctx(db_engine), now=now),
        return_exceptions=True,
    )
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert sorted(r for r in results if isinstance(r, int)) == [0, 4], (
        "exactly one run creates the four partitions"
    )
    existing = await _partitions(db_engine)
    assert sum(name.startswith("audit_logs_y2042m0") for name in existing) == 4


@pytest.mark.integration
async def test_a_year_boundary_creates_december_through_march(db_engine: AsyncEngine) -> None:
    created = await ensure_partitions(_ctx(db_engine), now=datetime(2043, 12, 31, 23, tzinfo=UTC))
    existing = await _partitions(db_engine)
    expected = [
        "audit_logs_y2043m12",
        "audit_logs_y2044m01",
        "audit_logs_y2044m02",
        "audit_logs_y2044m03",
    ]
    assert created == 4
    assert all(name in existing for name in expected)
    assert "audit_logs_y2044m04" not in existing
    low, high = await _bounds_utc(db_engine, "audit_logs_y2044m01")
    assert (low, high) == (
        datetime(2044, 1, 1, tzinfo=UTC),
        datetime(2044, 2, 1, tzinfo=UTC),
    )


@pytest.mark.integration
async def test_an_instant_that_is_already_next_month_somewhere_still_uses_the_utc_month(
    db_engine: AsyncEngine,
) -> None:
    """31 Jan 23:00 UTC is already 1 Feb in Kiritimati (+14): the UTC month wins."""
    from zoneinfo import ZoneInfo

    local = datetime(2045, 1, 31, 23, tzinfo=UTC).astimezone(ZoneInfo("Pacific/Kiritimati"))
    assert local.month == 2
    await ensure_partitions(_ctx(db_engine), now=local)
    assert "audit_logs_y2045m01" in await _partitions(db_engine)


@pytest.mark.integration
async def test_bounds_are_utc_whatever_the_session_timezone(db_engine: AsyncEngine) -> None:
    url = db_engine.url
    skewed = create_async_engine(url, connect_args={"server_settings": {"TimeZone": "Asia/Tokyo"}})
    try:
        async with skewed.connect() as conn:
            assert await conn.scalar(text("SHOW TimeZone")) == "Asia/Tokyo"
        await ensure_partitions(_ctx(skewed), now=datetime(2046, 7, 1, tzinfo=UTC))
    finally:
        await skewed.dispose()
    low, high = await _bounds_utc(db_engine, "audit_logs_y2046m07")
    assert (low, high) == (datetime(2046, 7, 1, tzinfo=UTC), datetime(2046, 8, 1, tzinfo=UTC))


@pytest.mark.integration
async def test_it_refuses_a_table_that_is_not_in_the_fixed_list(db_engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="not a partitioned table"):
        await ensure_partitions(_ctx(db_engine), ("users; DROP TABLE users",))


@pytest.mark.integration
async def test_it_only_touches_the_tables_it_is_given(db_engine: AsyncEngine) -> None:
    before = await _partitions(db_engine)
    assert await ensure_partitions(_ctx(db_engine), (), now=datetime(2047, 3, 1, tzinfo=UTC)) == 0
    assert await _partitions(db_engine) == before


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Through the application's own formatter (see test_deep_logs_and_leaks)."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    return buffer


@pytest.mark.integration
async def test_a_lock_timeout_is_logged_without_sql_and_does_not_raise(
    db_engine: AsyncEngine, captured_logs: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(partitions, "LOCK_TIMEOUT", "200ms")
    async with db_engine.connect() as conn:
        await conn.begin()
        # Any lock on the parent conflicts with the ACCESS EXCLUSIVE that
        # CREATE TABLE ... PARTITION OF needs.
        await conn.execute(text("LOCK TABLE audit_logs IN ACCESS SHARE MODE"))
        try:
            created = await ensure_partitions(_ctx(db_engine), now=datetime(2048, 9, 1, tzinfo=UTC))
        finally:
            await conn.rollback()

    assert created == 0
    logs = captured_logs.getvalue()
    assert "ensure_partitions_failed" in logs
    assert "audit_logs" in logs and "Error" in logs
    assert "CREATE TABLE" not in logs and "2048-09-01" not in logs
    # The next run retries and succeeds.
    assert await ensure_partitions(_ctx(db_engine), now=datetime(2048, 9, 1, tzinfo=UTC)) == 4


def test_the_worker_runs_it_monthly_and_at_startup() -> None:
    assert ensure_partitions in FUNCTIONS
    [job] = [j for j in CRON_JOBS if j.coroutine is ensure_partitions]
    assert job.run_at_startup is True
    assert job.day == 1


def test_partition_names_and_month_arithmetic() -> None:
    assert partition_name("audit_logs", date(2026, 1, 1)) == "audit_logs_y2026m01"
    assert partitions.months_to_ensure(datetime(2026, 11, 15, tzinfo=UTC)) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]
