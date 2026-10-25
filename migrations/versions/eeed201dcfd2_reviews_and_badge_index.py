"""reviews (VS-036, ADR-044; database-design.md 12.1) and the badge evidence's physical index on
order_items. Additive only. Revision ID: eeed201dcfd2, revises 595b7e6e2792."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "eeed201dcfd2"
down_revision: str | None = "595b7e6e2792"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "is_verified_purchase", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
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
        # RESTRICT: reviews are history; only verified users write, and the purge
        # deletes only never-verified accounts, so it can never meet one.
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_reviews_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="RESTRICT", name="fk_reviews_product_id"
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating_range"),
        sa.CheckConstraint(
            "body IS NULL OR (btrim(body) <> '' AND char_length(body) <= 2000)",
            name="ck_reviews_body_shape",
        ),
        sa.CheckConstraint("is_hidden = (hidden_at IS NOT NULL)", name="ck_reviews_hidden_shape"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_reviews_updated_after_created"),
    )
    # One live review per user and product (BR-101); a hidden review is live.
    op.create_index(
        "uq_reviews_user_product_live",
        "reviews",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # The public list and the rating aggregate: visible rows of one product.
    op.create_index(
        "ix_reviews_product_visible",
        "reviews",
        ["product_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL AND NOT is_hidden"),
    )
    op.create_index(
        "ix_reviews_user_live",
        "reviews",
        ["user_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Plan 4.1a: no index served the physical branch of the badge evidence.
    op.create_index(
        "ix_order_items_badge_received",
        "order_items",
        ["user_id", "product_id"],
        postgresql_where=sa.text(
            "product_type = 'physical' AND fulfillment_status IN ('delivered', 'picked_up')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_order_items_badge_received", table_name="order_items")
    op.drop_index("ix_reviews_user_live", table_name="reviews")
    op.drop_index("ix_reviews_product_visible", table_name="reviews")
    op.drop_index("uq_reviews_user_product_live", table_name="reviews")
    op.drop_table("reviews")
