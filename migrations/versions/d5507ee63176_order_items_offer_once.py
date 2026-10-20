"""An offer pays for at most one order line, ever (VS-041, ADR-037). Revision ID:
d5507ee63176, revises 8d2f6a1c3e57."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5507ee63176"
down_revision: str | None = "8d2f6a1c3e57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only a released (cancelled) unpaid line frees the offer; a refunded one never does.
    op.create_index(
        "uq_order_items_offer_once",
        "order_items",
        ["offer_id"],
        unique=True,
        postgresql_where=sa.text("offer_id IS NOT NULL AND fulfillment_status <> 'cancelled'"),
    )


def downgrade() -> None:
    op.drop_index("uq_order_items_offer_once", table_name="order_items")
