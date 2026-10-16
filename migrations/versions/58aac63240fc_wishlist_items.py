"""wishlist_items (VS-038): database-design.md 12.2, one live row per user and product.

Revision ID: 58aac63240fc, revises 2e89860f5274."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "58aac63240fc"
down_revision: str | None = "2e89860f5274"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE: the unverified-account purge must never be blocked (same
        # reasoning as notifications/addresses) - moot in practice, since
        # only a verified user can ever write a row, but kept consistent.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # RESTRICT: products are never hard-deleted (BR-018), same as product_images.
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    # The load-bearing constraint: at most one active row per user and
    # product, enforced by the database so a concurrent PUT cannot double-insert.
    op.create_index(
        "uq_wishlist_items_user_product_live",
        "wishlist_items",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Serves GET /me/wishlist's keyset pagination (-created_at, then id).
    op.create_index(
        "ix_wishlist_items_user_live",
        "wishlist_items",
        ["user_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Serves the admin analytics cross-check and any future per-product read.
    op.create_index(
        "ix_wishlist_items_product_live",
        "wishlist_items",
        ["product_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_wishlist_items_product_live", table_name="wishlist_items")
    op.drop_index("ix_wishlist_items_user_live", table_name="wishlist_items")
    op.drop_index("uq_wishlist_items_user_product_live", table_name="wishlist_items")
    op.drop_table("wishlist_items")
