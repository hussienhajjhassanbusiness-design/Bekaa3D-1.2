"""partition audit_logs by month (ADR-015)

Revision ID: c3d5e7f9a1b2
Revises: b7e4c1d9a2f6
Create Date: 2026-10-02 12:00:00.000000

`audit_logs` becomes a range-partitioned parent on `created_at`, one partition
per calendar month (UTC), with the primary key `(id, created_at)` PostgreSQL
requires of a partitioned table (database-design.md 13.2, 21.2).

Upgrade:

1. The plain table and everything it owns are renamed out of the way
   (`audit_logs_legacy`, `audit_logs_legacy_pkey`, ...), so the new parent can
   take the original names.
2. The partitioned parent is created with the same columns and defaults and the
   viewer-oriented indexes VS-012b will query by.
3. Monthly partitions `audit_logs_yYYYYmMM` are created from the month of the
   oldest row (the current month if there are none) through the current month
   + 3. Bounds are written with an explicit `+00`, so they mean the same instant
   whatever the session's TimeZone is. There is deliberately no DEFAULT
   partition: a row outside every partition must fail loudly rather than pile
   up somewhere that later blocks creating the real partition.
4. Every row is copied, the counts are compared - the migration aborts, and the
   transaction rolls back, if they differ - and the legacy table is dropped.

Downgrade reverses it: the parent's names are moved aside, the plain table is
recreated exactly as 42601a09ada6 + 5e1c0a7d2b94 left it, every row is copied
back and counted, and the parent is dropped with its partitions.

The partition DDL is inlined here rather than imported from the
`ensure_partitions` job: a migration must keep working however the application
code changes later.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: str | None = "b7e4c1d9a2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONTHS_AHEAD = 3

_COLUMNS = (
    "id, actor_user_id, action, entity_type, entity_id, "
    "before_data, after_data, request_id, ip_hash, created_at"
)

_PARTITIONED_INDEXES = {
    "ix_audit_logs_entity": "(entity_type, entity_id, created_at)",
    "ix_audit_logs_created_at_id": "(created_at, id)",
    "ix_audit_logs_actor_created_at": "(actor_user_id, created_at)",
    "ix_audit_logs_action_created_at": "(action, created_at)",
    "ix_audit_logs_request_id": "(request_id)",
}


def _first_of_month(value: datetime) -> date:
    utc = value.astimezone(UTC)
    return date(utc.year, utc.month, 1)


def _add_months(first: date, months: int) -> date:
    index = first.year * 12 + (first.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def _create_partition(start: date) -> None:
    end = _add_months(start, 1)
    name = f"audit_logs_y{start.year:04d}m{start.month:02d}"
    op.execute(
        f"CREATE TABLE {name} PARTITION OF audit_logs "
        f"FOR VALUES FROM ('{start.isoformat()} 00:00:00+00') "
        f"TO ('{end.isoformat()} 00:00:00+00')"
    )


def _count(table: str) -> int:
    return int(op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one())


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs RENAME TO audit_logs_legacy")
    op.execute(
        "ALTER TABLE audit_logs_legacy RENAME CONSTRAINT audit_logs_pkey TO audit_logs_legacy_pkey"
    )
    op.execute(
        "ALTER TABLE audit_logs_legacy RENAME CONSTRAINT audit_logs_actor_user_id_fkey "
        "TO audit_logs_legacy_actor_user_id_fkey"
    )
    op.execute("ALTER INDEX ix_audit_logs_entity RENAME TO ix_audit_logs_legacy_entity")

    op.execute(
        """
        CREATE TABLE audit_logs (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            actor_user_id UUID,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            before_data JSONB,
            after_data JSONB,
            request_id TEXT,
            ip_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT audit_logs_pkey PRIMARY KEY (id, created_at),
            CONSTRAINT audit_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id)
                REFERENCES users (id) ON DELETE SET NULL
        ) PARTITION BY RANGE (created_at)
        """
    )
    for name, columns in _PARTITIONED_INDEXES.items():
        op.execute(f"CREATE INDEX {name} ON audit_logs {columns}")

    bind = op.get_bind()
    oldest, newest, now = bind.execute(
        sa.text("SELECT min(created_at), max(created_at), now() FROM audit_logs_legacy")
    ).one()
    current = _first_of_month(now)
    first = _first_of_month(oldest) if oldest is not None else current
    last = max(_add_months(current, MONTHS_AHEAD), _first_of_month(newest) if newest else current)
    month = first
    while month <= last:
        _create_partition(month)
        month = _add_months(month, 1)

    op.execute(f"INSERT INTO audit_logs ({_COLUMNS}) SELECT {_COLUMNS} FROM audit_logs_legacy")
    legacy, copied = _count("audit_logs_legacy"), _count("audit_logs")
    if legacy != copied:
        raise RuntimeError(f"audit_logs partitioning copied {copied} of {legacy} rows; aborting")
    op.execute("DROP TABLE audit_logs_legacy")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs RENAME TO audit_logs_partitioned")
    op.execute(
        "ALTER TABLE audit_logs_partitioned RENAME CONSTRAINT audit_logs_pkey "
        "TO audit_logs_partitioned_pkey"
    )
    op.execute(
        "ALTER TABLE audit_logs_partitioned RENAME CONSTRAINT audit_logs_actor_user_id_fkey "
        "TO audit_logs_partitioned_actor_user_id_fkey"
    )
    for name in _PARTITIONED_INDEXES:
        op.execute(f"ALTER INDEX {name} RENAME TO {name}_partitioned")

    op.execute(
        """
        CREATE TABLE audit_logs (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            actor_user_id UUID,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            before_data JSONB,
            after_data JSONB,
            request_id TEXT,
            ip_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
            CONSTRAINT audit_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id)
                REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id)")

    op.execute(f"INSERT INTO audit_logs ({_COLUMNS}) SELECT {_COLUMNS} FROM audit_logs_partitioned")
    partitioned, copied = _count("audit_logs_partitioned"), _count("audit_logs")
    if partitioned != copied:
        raise RuntimeError(
            f"audit_logs un-partitioning copied {copied} of {partitioned} rows; aborting"
        )
    op.execute("DROP TABLE audit_logs_partitioned")
