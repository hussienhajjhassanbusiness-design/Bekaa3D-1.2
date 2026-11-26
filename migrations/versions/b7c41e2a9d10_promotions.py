"""promotions and promotion_products: administrator-created seasonal price campaigns.

Revision ID: b7c41e2a9d10, revises 95ffee5fde3b."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c41e2a9d10"
down_revision: str | None = "95ffee5fde3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from models: a migration is frozen history.
_ENUMS: dict[str, tuple[str, ...]] = {
    "promotion_discount_type": ("percentage", "fixed"),
    "promotion_scope": ("all", "physical", "stl", "selected"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    for name in _ENUMS:
        postgresql.ENUM(*_ENUMS[name], name=name).create(bind)

    op.create_table(
        "promotions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("badge_text", sa.Text(), nullable=True),
        sa.Column("discount_type", _enum("promotion_discount_type"), nullable=False),
        sa.Column("discount_value", sa.BigInteger(), nullable=False),
        sa.Column("scope", _enum("promotion_scope"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_promotions_name_not_blank"),
        sa.CheckConstraint(
            "badge_text IS NULL OR btrim(badge_text) <> ''", name="ck_promotions_badge_not_blank"
        ),
        sa.CheckConstraint("discount_value > 0", name="ck_promotions_discount_positive"),
        sa.CheckConstraint(
            "discount_type <> 'percentage' OR discount_value <= 100",
            name="ck_promotions_percentage_range",
        ),
        sa.CheckConstraint("starts_at < ends_at", name="ck_promotions_window_order"),
    )
    op.create_index(
        "ix_promotions_active_window",
        "promotions",
        ["starts_at", "ends_at"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "promotion_products",
        sa.Column("promotion_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("promotion_id", "product_id"),
        sa.ForeignKeyConstraint(["promotion_id"], ["promotions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_promotion_products_product", "promotion_products", ["product_id"])


def downgrade() -> None:
    op.drop_table("promotion_products")
    op.drop_table("promotions")
    for name in reversed(list(_ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
