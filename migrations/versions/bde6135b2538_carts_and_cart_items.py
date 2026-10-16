"""carts and cart_items (VS-022, ADR-029): database-design.md 8.1-8.2, plus a type
snapshot whose CHECK keeps an STL line at quantity 1.

Revision ID: bde6135b2538, revises 75ad58ebd9e5."""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "bde6135b2538"
down_revision: str | None = "75ad58ebd9e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Owned by `products` (fc18b48a1780): reused here, never created or dropped.
_PRODUCT_TYPE = postgresql.ENUM("physical", "stl", name="product_type", create_type=False)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    # The target of cart_items' composite FK; `id` is already unique, so this cannot fail.
    op.create_unique_constraint("uq_products_id_type", "products", ["id", "type"])

    op.create_table(
        "carts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE: no FK to users may block the never-verified purge.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_carts_user_id"),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("cart_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("product_type", _PRODUCT_TYPE, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_snapshot_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="CASCADE"),
        # The snapshot always equals the product's real type; a type change is blocked.
        sa.ForeignKeyConstraint(
            ["product_id", "product_type"],
            ["products.id", "products.type"],
            name="fk_cart_items_product_type",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.UniqueConstraint("cart_id", "product_id", name="uq_cart_items_cart_product"),
        sa.CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        sa.CheckConstraint(
            "product_type <> 'stl' OR quantity = 1", name="ck_cart_items_stl_quantity_one"
        ),
        sa.CheckConstraint(
            "price_snapshot_cents >= 0", name="ck_cart_items_price_snapshot_non_negative"
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_cart_items_currency_usd"),
    )


def downgrade() -> None:
    # cart_items first: its composite FK depends on uq_products_id_type.
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_constraint("uq_products_id_type", "products", type_="unique")
