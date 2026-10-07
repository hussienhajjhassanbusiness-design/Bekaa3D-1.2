"""audit_logs.created_at defaults to clock_timestamp()

Revision ID: 5e1c0a7d2b94
Revises: a9c0aec909a9
Create Date: 2026-09-30

BUG-35. `now()` is the *transaction start* time. Under contention a transaction
can start before another yet take the row lock after it, so the audit log's
chronological order contradicted the real order of changes (a change was
timestamped before the change it overwrote). `clock_timestamp()` is the time of
the INSERT itself, which - because every audited mutation writes its row after
taking the row lock - follows the order in which changes actually happened.

Additive: only the column default changes; existing rows are untouched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5e1c0a7d2b94"
down_revision: str | None = "a9c0aec909a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs ALTER COLUMN created_at SET DEFAULT clock_timestamp()")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs ALTER COLUMN created_at SET DEFAULT now()")
