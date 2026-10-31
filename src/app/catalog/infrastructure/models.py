import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.domain.enums import AcceptedPaymentMethods, ProductType, PurchaseMode
from app.core.database import Base

# No `onupdate` on `updated_at`: the application writes it, so a no-op PATCH
# leaves it alone. Constraint and index names match the migrations; the
# repositories match violations by name, so they must not drift.

LIVE = text("deleted_at IS NULL")

# Archiving sets `deleted_at` and clears `is_active` in one step (the domain's
# `archive()`); this makes the database refuse the contradictory "archived but
# still active" row as well, whoever writes it.
_ARCHIVED_NOT_ACTIVE = "deleted_at IS NULL OR NOT is_active"


class CategoryModel(Base):
    """database-design.md 6.1. V1 has no hierarchy, so there is no `parent_id`."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # `UNIQUE(slug) WHERE deleted_at IS NULL` - the exact constraint
        # database-design.md 6.1 specifies. Being partial is what implements
        # "soft-deleting a category releases its slug": an archived row drops
        # out of the index, so the slug becomes available again without any
        # cleanup step.
        Index("ix_categories_live_slug", "slug", unique=True, postgresql_where=LIVE),
        # The same rule, case-insensitively. The application lowercases slugs
        # before writing, but only this index stops a writer that does not
        # (SQL, a future importer) from storing "Lamps" beside "lamps".
        Index(
            "ix_categories_live_slug_ci",
            func.lower(text("slug")),
            unique=True,
            postgresql_where=LIVE,
        ),
        CheckConstraint(_ARCHIVED_NOT_ACTIVE, name="ck_categories_archived_not_active"),
    )


class MaterialModel(Base):
    """database-design.md 6.2. No slug - a material is never addressed by URL.

    Live names are unique **case-insensitively**: materials are facet values,
    and "PLA" beside "pla" would split one storefront filter into two (SRS 592).
    The index is partial, so archiving a value releases its name for reuse.
    """

    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_materials_live_name_ci",
            func.lower(text("name")),
            unique=True,
            postgresql_where=LIVE,
        ),
        CheckConstraint(_ARCHIVED_NOT_ACTIVE, name="ck_materials_archived_not_active"),
    )


class ColourModel(Base):
    """database-design.md 6.3. Identical shape and rules to materials."""

    __tablename__ = "colours"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_colours_live_name_ci",
            func.lower(text("name")),
            unique=True,
            postgresql_where=LIVE,
        ),
        CheckConstraint(_ARCHIVED_NOT_ACTIVE, name="ck_colours_archived_not_active"),
    )


# Physical-only columns: all NULL on an STL row (SRS 6.2, database-design.md 6.4).
PHYSICAL_ONLY_COLUMNS = (
    "purchase_mode",
    "accepted_payment_methods",
    "material_id",
    "colour_id",
    "dimensions",
    "production_lead_time_days",
    "batch_size",
    "max_quantity_per_line",
    "weight_grams",
)
PHYSICAL_REQUIRED_COLUMNS = (
    "purchase_mode",
    "accepted_payment_methods",
    "production_lead_time_days",
    "batch_size",
    "max_quantity_per_line",
)
TYPE_INTEGRITY = (
    "(type = 'physical' AND "
    + " AND ".join(f"{c} IS NOT NULL" for c in PHYSICAL_REQUIRED_COLUMNS)
    + ") OR (type = 'stl' AND "
    + " AND ".join(f"{c} IS NULL" for c in PHYSICAL_ONLY_COLUMNS)
    + ")"
)
SLUG_FORMAT = "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'"
# Exactly the three keys, each a positive integer; CASE keeps casts behind type checks.
DIMENSIONS_SHAPE = (
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
SEARCH_VECTOR = (
    "setweight(to_tsvector('english'::regconfig, name), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'B')"
)
LIVE_VISIBLE = text("deleted_at IS NULL AND is_visible")


def _enum(
    enum_type: type[ProductType] | type[PurchaseMode] | type[AcceptedPaymentMethods], name: str
) -> Enum:
    return Enum(enum_type, name=name, values_callable=lambda e: [m.value for m in e])


class ProductModel(Base):
    """database-design.md 6.4, plus `version` for optimistic concurrency (ADR-020)."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    type: Mapped[ProductType] = mapped_column(_enum(ProductType, "product_type"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    seo_title: Mapped[str | None] = mapped_column(Text)
    seo_description: Mapped[str | None] = mapped_column(Text)
    og_image_url: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR, persisted=True), nullable=False
    )
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    average_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0")
    )
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    wishlist_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    purchase_mode: Mapped[PurchaseMode | None] = mapped_column(_enum(PurchaseMode, "purchase_mode"))
    accepted_payment_methods: Mapped[AcceptedPaymentMethods | None] = mapped_column(
        _enum(AcceptedPaymentMethods, "accepted_payment_methods")
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="RESTRICT")
    )
    colour_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("colours.id", ondelete="RESTRICT")
    )
    # none_as_null: Python None must be SQL NULL, not JSON null, for the type CHECK.
    dimensions: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    production_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    max_quantity_per_line: Mapped[int | None] = mapped_column(Integer)
    weight_grams: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(TYPE_INTEGRITY, name="ck_products_type_integrity"),
        # VS-022: the target of cart_items' (product_id, product_type) foreign key.
        UniqueConstraint("id", "type", name="uq_products_id_type"),
        CheckConstraint("price_cents >= 0", name="ck_products_price_non_negative"),
        CheckConstraint("currency = 'USD'", name="ck_products_currency_usd"),
        CheckConstraint("btrim(name) <> ''", name="ck_products_name_not_blank"),
        CheckConstraint(SLUG_FORMAT, name="ck_products_slug_format"),
        CheckConstraint(
            "average_rating >= 0 AND average_rating <= 5", name="ck_products_rating_range"
        ),
        CheckConstraint("review_count >= 0", name="ck_products_review_count_non_negative"),
        CheckConstraint("wishlist_count >= 0", name="ck_products_wishlist_count_non_negative"),
        CheckConstraint(
            "production_lead_time_days >= 0", name="ck_products_lead_time_non_negative"
        ),
        CheckConstraint("batch_size > 0", name="ck_products_batch_size_positive"),
        CheckConstraint("max_quantity_per_line > 0", name="ck_products_max_quantity_positive"),
        CheckConstraint("weight_grams > 0", name="ck_products_weight_positive"),
        CheckConstraint(DIMENSIONS_SHAPE, name="ck_products_dimensions_shape"),
        CheckConstraint("version >= 1", name="ck_products_version_positive"),
        Index("ix_products_live_slug", "slug", unique=True, postgresql_where=LIVE),
        Index("ix_products_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # database-design.md 19.1 storefront paths, created now so VS-015 needs no migration.
        Index(
            "ix_products_browse_category",
            "type",
            "category_id",
            "price_cents",
            postgresql_where=LIVE_VISIBLE,
        ),
        Index(
            "ix_products_browse_facets",
            "type",
            "material_id",
            "colour_id",
            "price_cents",
            postgresql_where=LIVE_VISIBLE,
        ),
        Index(
            "ix_products_browse_rating",
            text("average_rating DESC"),
            postgresql_where=LIVE_VISIBLE,
        ),
        Index("ix_products_browse_newest", text("created_at DESC"), postgresql_where=LIVE_VISIBLE),
        # The archive guard's "does a live product use this value?" lookups.
        Index("ix_products_live_category", "category_id", postgresql_where=LIVE),
        Index("ix_products_live_material", "material_id", postgresql_where=LIVE),
        Index("ix_products_live_colour", "colour_id", postgresql_where=LIVE),
    )


# Generated keys only: `products/<uuid4>.<ext>`, never a client filename (path traversal).
STORAGE_KEY_FORMAT = (
    "storage_key ~ '^products/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    "[.](jpg|png|webp)$'"
)


class ProductImageModel(Base):
    """database-design.md 6.5; rules in docs/product-images.md."""

    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_product_images_storage_key"),
        CheckConstraint(STORAGE_KEY_FORMAT, name="ck_product_images_storage_key_format"),
        CheckConstraint("sort_order >= 0", name="ck_product_images_sort_order_non_negative"),
        CheckConstraint(
            "deleted_at IS NULL OR NOT is_cover", name="ck_product_images_deleted_not_cover"
        ),
        Index(
            "ix_product_images_live_cover",
            "product_id",
            unique=True,
            postgresql_where=text("is_cover AND deleted_at IS NULL"),
        ),
        Index(
            "ix_product_images_live_order",
            "product_id",
            "sort_order",
            postgresql_where=LIVE,
        ),
    )
