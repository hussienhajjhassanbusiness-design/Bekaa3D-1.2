"""When the customer cancelled the order themselves (VS-031; ADR-038 d23): a cash order so
cancelled counts toward `cash_max_open_orders` for 24 hours. Revision ID: 595b7e6e2792,
revises 80e56abf0969."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "595b7e6e2792"
down_revision: str | None = "80e56abf0969"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SELF_CANCELLED_CASH = "payment_method = 'cash' AND customer_cancelled_at IS NOT NULL"


def upgrade() -> None:
    op.add_column("orders", sa.Column("customer_cancelled_at", postgresql.TIMESTAMP(timezone=True)))
    op.create_index(
        "ix_orders_cash_self_cancel_user",
        "orders",
        ["user_id", "customer_cancelled_at"],
        postgresql_where=sa.text(_SELF_CANCELLED_CASH),
    )
    op.create_index(
        "ix_orders_cash_self_cancel_phone",
        "orders",
        ["contact_phone_hash", "customer_cancelled_at"],
        postgresql_where=sa.text(_SELF_CANCELLED_CASH),
    )


def downgrade() -> None:
    op.drop_index("ix_orders_cash_self_cancel_phone", table_name="orders")
    op.drop_index("ix_orders_cash_self_cancel_user", table_name="orders")
    op.drop_column("orders", "customer_cancelled_at")
