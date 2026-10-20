"""offers.remind_at (when the "expiring soon" email is due) and the agreed price bounded by
the amount accepted (VS-040, ADR-035). Revision ID: 8d2f6a1c3e57, revises 4b7e2c9d1f30."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8d2f6a1c3e57"
down_revision: str | None = "4b7e2c9d1f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("remind_at", postgresql.TIMESTAMP(timezone=True)))
    # Only the customer is reminded (SRS 16.1); cleared once sent or when the turn ends.
    op.create_check_constraint(
        "ck_offers_remind_at_awaiting_customer",
        "offers",
        "remind_at IS NULL OR status = 'awaiting_customer'",
    )
    # Accept takes min(amount on the table, list price), and nothing raises it afterwards.
    op.create_check_constraint(
        "ck_offers_agreed_within_current",
        "offers",
        "agreed_amount_cents IS NULL OR agreed_amount_cents <= current_amount_cents",
    )
    op.create_index(
        "ix_offers_remind_at",
        "offers",
        ["remind_at"],
        postgresql_where=sa.text("remind_at IS NOT NULL"),
    )
    # 75 % of the way from the turn's start (its last update) to its deadline.
    op.execute(
        "UPDATE offers SET remind_at = responds_by - (responds_by - updated_at) / 4 "
        "WHERE status = 'awaiting_customer'"
    )


def downgrade() -> None:
    op.drop_index("ix_offers_remind_at", table_name="offers")
    op.drop_constraint("ck_offers_agreed_within_current", "offers", type_="check")
    op.drop_constraint("ck_offers_remind_at_awaiting_customer", "offers", type_="check")
    op.drop_column("offers", "remind_at")
