"""Seed `manual_max_open_orders` (VS-050 audit Q-1, ADR-049 d14).

Revision ID: 95ffee5fde3b, revises 941b40d285ce."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "95ffee5fde3b"
down_revision: str | None = "941b40d285ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from models: a migration is frozen history.
_settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    sa.column(
        "type",
        postgresql.ENUM(
            "boolean",
            "integer",
            "string",
            "money",
            "duration",
            "json",
            name="setting_type",
            create_type=False,
        ),
    ),
    sa.column("value", postgresql.JSONB(none_as_null=False)),
    sa.column("description", sa.Text),
)
_KEY = "manual_max_open_orders"


def upgrade() -> None:
    op.execute(
        postgresql.insert(_settings)
        .values(
            key=_KEY,
            type="integer",
            value=3,
            description=(
                "Unpaid orders awaiting the administrator's call on the manual payment "
                "provider allowed per customer at once (ADR-049)."
            ),
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )


def downgrade() -> None:
    op.execute(sa.delete(_settings).where(_settings.c.key == _KEY))
