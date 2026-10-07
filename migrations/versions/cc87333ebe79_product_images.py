"""product_images (VS-014): database-design.md 6.5, one live cover per product.

Revision ID: cc87333ebe79, revises fc18b48a1780."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cc87333ebe79"
down_revision: str | None = "fc18b48a1780"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STORAGE_KEY_FORMAT = (
    "storage_key ~ '^products/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    "[.](jpg|png|webp)$'"
)


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_cover", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_product_images_storage_key"),
        sa.CheckConstraint(_STORAGE_KEY_FORMAT, name="ck_product_images_storage_key_format"),
        sa.CheckConstraint("sort_order >= 0", name="ck_product_images_sort_order_non_negative"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR NOT is_cover", name="ck_product_images_deleted_not_cover"
        ),
    )
    op.create_index(
        "ix_product_images_live_cover",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_cover AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_product_images_live_order",
        "product_images",
        ["product_id", "sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_product_images_live_order", table_name="product_images")
    op.drop_index("ix_product_images_live_cover", table_name="product_images")
    op.drop_table("product_images")
