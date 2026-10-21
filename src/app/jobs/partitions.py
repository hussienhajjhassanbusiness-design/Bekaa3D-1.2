"""Keep monthly range partitions created ahead of time (ADR-015, SRS 23).

`audit_logs` has no DEFAULT partition (migration c3d5e7f9a1b2), so an insert for
a month with no partition fails - and every login, admin action and setting
change writes an audit row. This job is what keeps that from ever happening: it
makes sure the current month and the next `MONTHS_AHEAD` months exist, at worker
start and on the first of every month.

The set of tables is a fixed code-level tuple. Table names are interpolated
into DDL (identifiers cannot be bound parameters), which is safe only because
they never come from input; `ensure_partitions` refuses any name not in
`PARTITIONED_TABLES`.

Concurrency: one transaction, serialised by a transaction-scoped advisory lock,
so two workers (or a worker start racing the monthly tick) cannot both try to
create the same partition. `CREATE TABLE ... PARTITION OF` takes an ACCESS
EXCLUSIVE lock on the parent, so `lock_timeout` bounds how long the job may sit
queued behind a long transaction - and, more importantly, how long audit inserts
may queue behind *it*. On timeout or any database error the job logs the table
and the error class, and returns: the next run retries, and a failure must never
take worker startup down with it.
"""

from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger()

PARTITIONED_TABLES: tuple[str, ...] = ("audit_logs",)
MONTHS_AHEAD = 3
LOCK_TIMEOUT = "5s"
# Distinct from the last-administrator lock (identity/domain/administrators.py).
ENSURE_PARTITIONS_LOCK_KEY = 0x62656B6150415254  # "bekaPART"


def first_of_month(moment: datetime) -> date:
    utc = moment.astimezone(UTC)
    return date(utc.year, utc.month, 1)


def add_months(first: date, months: int) -> date:
    index = first.year * 12 + (first.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def months_to_ensure(now: datetime) -> list[date]:
    """The current UTC month and the `MONTHS_AHEAD` after it."""
    current = first_of_month(now)
    return [add_months(current, n) for n in range(MONTHS_AHEAD + 1)]


def partition_name(table: str, month: date) -> str:
    return f"{table}_y{month.year:04d}m{month.month:02d}"


def _create_sql(table: str, month: date) -> str:
    # Explicit +00: the bound is the same instant whatever the session TimeZone.
    return (
        f'CREATE TABLE IF NOT EXISTS "{partition_name(table, month)}" '
        f'PARTITION OF "{table}" '
        f"FOR VALUES FROM ('{month.isoformat()} 00:00:00+00') "
        f"TO ('{add_months(month, 1).isoformat()} 00:00:00+00')"
    )


async def ensure_partitions(
    ctx: dict[str, Any],
    tables: tuple[str, ...] = PARTITIONED_TABLES,
    *,
    now: datetime | None = None,
) -> int:
    """arq job. Returns how many partitions it created (0 on a no-op or failure)."""
    unknown = [t for t in tables if t not in PARTITIONED_TABLES]
    if unknown:
        raise ValueError(f"not a partitioned table: {unknown}")
    months = months_to_ensure(now or datetime.now(UTC))

    created: list[str] = []
    current_table = None
    try:
        async with ctx["session_factory"]() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": ENSURE_PARTITIONS_LOCK_KEY}
            )
            await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
            for current_table in tables:
                for month in months:
                    name = partition_name(current_table, month)
                    if await session.scalar(text("SELECT to_regclass(:name)"), {"name": name}):
                        continue
                    await session.execute(text(_create_sql(current_table, month)))
                    created.append(name)
    except (SQLAlchemyError, OSError) as exc:
        # The class only: a driver message can carry the statement and its values.
        await logger.awarning(
            "ensure_partitions_failed", table=current_table, error=type(exc).__name__
        )
        return 0

    if created:
        await logger.ainfo("partitions_created", partitions=created)
    return len(created)
