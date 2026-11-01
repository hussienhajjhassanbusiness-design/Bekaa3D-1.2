"""The `manual` payment provider and its hold setting (VS-050, ADR-049).

Revision ID: 941b40d285ce, revises 089f97a72014."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "941b40d285ce"
down_revision: str | None = "089f97a72014"
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
_HOLD_KEY = "manual_payment_hold_period"
_NEVER_PROCESSING = "provider <> 'manual' OR status <> 'processing'"


def upgrade() -> None:
    # A new enum value cannot be used in the transaction that adds it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'manual'")
    op.create_check_constraint("ck_payments_manual_never_processing", "payments", _NEVER_PROCESSING)
    op.create_index(
        "ix_payments_awaiting_manual",
        "payments",
        ["initiated_at", "id"],
        postgresql_where=sa.text("provider = 'manual' AND status = 'pending'"),
    )
    op.execute(
        postgresql.insert(_settings)
        .values(
            key=_HOLD_KEY,
            type="duration",
            value=604_800,  # 7 days
            description=(
                "Seconds an unpaid order on the manual payment provider is held before it "
                "is released."
            ),
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; `manual` stays in `payment_provider`, unused.
    op.execute(sa.delete(_settings).where(_settings.c.key == _HOLD_KEY))
    op.drop_index("ix_payments_awaiting_manual", table_name="payments")
    op.drop_constraint("ck_payments_manual_never_processing", "payments", type_="check")
