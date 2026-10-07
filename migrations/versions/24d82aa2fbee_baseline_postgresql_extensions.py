"""baseline postgresql extensions

Revision ID: 24d82aa2fbee
Revises:
Create Date: 2026-08-12 02:11:18.139165

"""

from collections.abc import Sequence

from alembic import op

revision: str = "24d82aa2fbee"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXTENSIONS = ("pgcrypto", "citext", "pg_trgm", "unaccent", "btree_gin")


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")


def downgrade() -> None:
    for extension in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {extension}")
