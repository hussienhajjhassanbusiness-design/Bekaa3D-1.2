"""Problem reports (VS-029b, ADR-041): `contact_messages.user_id` and `order_id`, and
receipt feedback on physical lines only. Revision ID: 0f43e238eaae, revises b6e1d0c4a2f7."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0f43e238eaae"
down_revision: str | None = "b6e1d0c4a2f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contact_messages", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("contact_messages", sa.Column("order_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_contact_messages_user_id",
        "contact_messages",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",  # database-design.md 14; a report's owner is held by orders
    )
    op.create_foreign_key(
        "fk_contact_messages_order_id",
        "contact_messages",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # A problem report is always a signed-in customer's (ADR-041 d3).
    op.create_check_constraint(
        "ck_contact_messages_order_has_user",
        "contact_messages",
        "order_id IS NULL OR user_id IS NOT NULL",
    )
    op.create_index(
        "ix_contact_messages_order_id",
        "contact_messages",
        ["order_id"],
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index(
        "ix_contact_messages_user_id",
        "contact_messages",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_order_items_feedback_physical_only",
        "order_items",
        "product_type = 'physical' "
        "OR (receipt_confirmed_at IS NULL AND problem_reported_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_order_items_feedback_physical_only", "order_items", type_="check")
    op.drop_index("ix_contact_messages_user_id", table_name="contact_messages")
    op.drop_index("ix_contact_messages_order_id", table_name="contact_messages")
    op.drop_constraint("ck_contact_messages_order_has_user", "contact_messages", type_="check")
    op.drop_constraint("fk_contact_messages_order_id", "contact_messages", type_="foreignkey")
    op.drop_constraint("fk_contact_messages_user_id", "contact_messages", type_="foreignkey")
    op.drop_column("contact_messages", "order_id")
    op.drop_column("contact_messages", "user_id")
