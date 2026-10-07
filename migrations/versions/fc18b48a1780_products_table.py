"""products table (VS-013): database-design.md 6.4 plus `version` (ADR-020).

Revision ID: fc18b48a1780, revises c3d5e7f9a1b2."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fc18b48a1780"
down_revision: str | None = "c3d5e7f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = sa.text("deleted_at IS NULL")
_LIVE_VISIBLE = sa.text("deleted_at IS NULL AND is_visible")

# Frozen copies, not imports from the model: a migration must not change when the code does.
_TYPE_INTEGRITY = (
    "(type = 'physical' AND purchase_mode IS NOT NULL AND production_lead_time_days IS NOT NULL"
    " AND batch_size IS NOT NULL AND max_quantity_per_line IS NOT NULL)"
    " OR (type = 'stl' AND purchase_mode IS NULL AND material_id IS NULL AND colour_id IS NULL"
    " AND dimensions IS NULL AND production_lead_time_days IS NULL AND batch_size IS NULL"
    " AND max_quantity_per_line IS NULL AND weight_grams IS NULL)"
)
_DIMENSIONS_SHAPE = (
    "dimensions IS NULL OR CASE WHEN jsonb_typeof(dimensions) = 'object' THEN "
    "dimensions - ARRAY['length_mm', 'width_mm', 'height_mm'] = '{}'::jsonb AND "
    + " AND ".join(
        f"CASE WHEN jsonb_typeof(dimensions -> '{k}') = 'number' "
        f"THEN (dimensions ->> '{k}')::numeric > 0 "
        f"AND (dimensions ->> '{k}')::numeric = trunc((dimensions ->> '{k}')::numeric) "
        "ELSE false END"
        for k in ("length_mm", "width_mm", "height_mm")
    )
    + " ELSE false END"
)
_SEARCH_VECTOR = (
    "setweight(to_tsvector('english'::regconfig, name), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'B')"
)

_CHECKS = (
    (_TYPE_INTEGRITY, "ck_products_type_integrity"),
    ("price_cents >= 0", "ck_products_price_non_negative"),
    ("currency = 'USD'", "ck_products_currency_usd"),
    ("btrim(name) <> ''", "ck_products_name_not_blank"),
    ("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", "ck_products_slug_format"),
    ("average_rating >= 0 AND average_rating <= 5", "ck_products_rating_range"),
    ("review_count >= 0", "ck_products_review_count_non_negative"),
    ("wishlist_count >= 0", "ck_products_wishlist_count_non_negative"),
    ("production_lead_time_days >= 0", "ck_products_lead_time_non_negative"),
    ("batch_size > 0", "ck_products_batch_size_positive"),
    ("max_quantity_per_line > 0", "ck_products_max_quantity_positive"),
    ("weight_grams > 0", "ck_products_weight_positive"),
    (_DIMENSIONS_SHAPE, "ck_products_dimensions_shape"),
    ("version >= 1", "ck_products_version_positive"),
)

_INDEXES = (
    "ix_products_live_slug",
    "ix_products_search_vector",
    "ix_products_name_trgm",
    "ix_products_browse_category",
    "ix_products_browse_facets",
    "ix_products_browse_rating",
    "ix_products_browse_newest",
    "ix_products_live_category",
    "ix_products_live_material",
    "ix_products_live_colour",
)


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("type", sa.Enum("physical", "stl", name="product_type"), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("seo_title", sa.Text(), nullable=True),
        sa.Column("seo_description", sa.Text(), nullable=True),
        sa.Column("og_image_url", sa.Text(), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_SEARCH_VECTOR, persisted=True),
            nullable=False,
        ),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="USD", nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "average_rating",
            sa.Numeric(precision=3, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("review_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("wishlist_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "purchase_mode",
            sa.Enum("online_only", "whatsapp_only", "both", name="purchase_mode"),
            nullable=True,
        ),
        sa.Column("material_id", sa.UUID(), nullable=True),
        sa.Column("colour_id", sa.UUID(), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("production_lead_time_days", sa.Integer(), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("max_quantity_per_line", sa.Integer(), nullable=True),
        sa.Column("weight_grams", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["colour_id"], ["colours.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        *(sa.CheckConstraint(sql, name=name) for sql, name in _CHECKS),
    )
    op.create_index(
        "ix_products_live_slug", "products", ["slug"], unique=True, postgresql_where=_LIVE
    )
    op.create_index(
        "ix_products_search_vector", "products", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_browse_category",
        "products",
        ["type", "category_id", "price_cents"],
        postgresql_where=_LIVE_VISIBLE,
    )
    op.create_index(
        "ix_products_browse_facets",
        "products",
        ["type", "material_id", "colour_id", "price_cents"],
        postgresql_where=_LIVE_VISIBLE,
    )
    op.create_index(
        "ix_products_browse_rating",
        "products",
        [sa.literal_column("average_rating DESC")],
        postgresql_where=_LIVE_VISIBLE,
    )
    op.create_index(
        "ix_products_browse_newest",
        "products",
        [sa.literal_column("created_at DESC")],
        postgresql_where=_LIVE_VISIBLE,
    )
    for column in ("category", "material", "colour"):
        op.create_index(
            f"ix_products_live_{column}", "products", [f"{column}_id"], postgresql_where=_LIVE
        )


def downgrade() -> None:
    for name in reversed(_INDEXES):
        op.drop_index(name, table_name="products")
    op.drop_table("products")
    # create_table made the enum types; drop_table leaves them behind.
    for enum_name in ("purchase_mode", "product_type"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
