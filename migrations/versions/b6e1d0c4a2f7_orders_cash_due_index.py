"""The admin order queue's partial indexes (VS-029, SRS 8.7). Revision ID: b6e1d0c4a2f7,
revises 7a1c3e9b5d24."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1d0c4a2f7"
down_revision: str | None = "7a1c3e9b5d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An unpaid, uncancelled cash order is exactly this predicate (VS-028 plan D8).
    op.create_index(
        "ix_orders_cash_due",
        "orders",
        [sa.text("placed_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("payment_method = 'cash' AND status = 'in_progress'"),
    )
    # The queue never lists an unpaid online order, open or released (BR-148, ADR-040).
    op.create_index(
        "ix_orders_admin_queue",
        "orders",
        [sa.text("placed_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text(
            "status <> 'pending_payment' AND (payment_method = 'cash' OR cancelled_at IS NULL)"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_orders_admin_queue", table_name="orders")
    op.drop_index("ix_orders_cash_due", table_name="orders")
