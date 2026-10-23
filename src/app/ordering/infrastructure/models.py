import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.application.ports import ProductType
from app.core.database import Base
from app.ordering.domain.enums import (
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)

# Lowercase hex HMAC-SHA256 (`app.core.security.hash_phone`, ADR-024 d6).
PHONE_HASH_FORMAT = "^[0-9a-f]{64}$"
# Every order but an unpaid online one, open or released (BR-148; ADR-040).
ADMIN_QUEUE_PREDICATE = (
    "status <> 'pending_payment' AND (payment_method = 'cash' OR cancelled_at IS NULL)"
)


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """A PostgreSQL type created by a migration, never by the ORM."""
    return Enum(enum, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])


class CartModel(Base):
    """database-design.md 8.1; migration bde6135b2538."""

    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_carts_user_id"),)


class CartItemModel(Base):
    """database-design.md 8.2 plus the `product_type` snapshot (ADR-029)."""

    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(
            ProductType,
            name="product_type",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_snapshot_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "product_type"],
            ["products.id", "products.type"],
            name="fk_cart_items_product_type",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("cart_id", "product_id", name="uq_cart_items_cart_product"),
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        CheckConstraint(
            "product_type <> 'stl' OR quantity = 1", name="ck_cart_items_stl_quantity_one"
        ),
        CheckConstraint(
            "price_snapshot_cents >= 0", name="ck_cart_items_price_snapshot_non_negative"
        ),
        CheckConstraint("currency = 'USD'", name="ck_cart_items_currency_usd"),
    )


class OrderModel(Base):
    """database-design.md 8.3 plus `digital_terms_version` (Q18); migration 03a4730dd046."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_number: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    customer_email_snapshot: Mapped[str] = mapped_column(CITEXT, nullable=False)
    source: Mapped[OrderSource] = mapped_column(
        _pg_enum(OrderSource, "order_source"), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        _pg_enum(OrderStatus, "order_status"), nullable=False
    )
    fulfillment_method: Mapped[FulfillmentMethod | None] = mapped_column(
        _pg_enum(FulfillmentMethod, "fulfillment_method")
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _pg_enum(PaymentMethod, "payment_method"), nullable=False
    )
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    recipient_name: Mapped[str | None] = mapped_column(Text)
    contact_phone_snapshot: Mapped[str | None] = mapped_column(Text)
    contact_phone_hash: Mapped[str | None] = mapped_column(Text)
    governorate: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    landmark_notes: Mapped[str | None] = mapped_column(Text)
    customer_note: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    estimated_dispatch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    digital_terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    digital_terms_version: Mapped[str | None] = mapped_column(Text)
    cash_terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        UniqueConstraint("id", "payment_method", name="uq_orders_id_payment_method"),
        CheckConstraint(
            "subtotal_cents >= 0 AND total_cents >= 0", name="ck_orders_money_non_negative"
        ),
        CheckConstraint("tax_cents = 0", name="ck_orders_tax_zero"),
        CheckConstraint(
            "total_cents = subtotal_cents + tax_cents", name="ck_orders_total_arithmetic"
        ),
        CheckConstraint("currency = 'USD'", name="ck_orders_currency_usd"),
        CheckConstraint(
            "fulfillment_method IS NULL OR contact_phone_snapshot IS NOT NULL",
            name="ck_orders_physical_has_phone",
        ),
        CheckConstraint(
            "fulfillment_method IS NOT NULL OR payment_method = 'online'",
            name="ck_orders_digital_only_online",
        ),
        CheckConstraint(
            "payment_method <> 'cash' OR cash_terms_accepted_at IS NOT NULL",
            name="ck_orders_cash_terms",
        ),
        CheckConstraint(
            "fulfillment_method IS DISTINCT FROM 'delivery' OR (recipient_name IS NOT NULL "
            "AND governorate IS NOT NULL AND city IS NOT NULL AND landmark_notes IS NOT NULL)",
            name="ck_orders_delivery_address",
        ),
        CheckConstraint(
            "(contact_phone_snapshot IS NULL) = (contact_phone_hash IS NULL)",
            name="ck_orders_phone_hash_pair",
        ),
        CheckConstraint(
            "(digital_terms_accepted_at IS NULL) = (digital_terms_version IS NULL)",
            name="ck_orders_digital_terms_version",
        ),
        # VS-028 (fcd589e89e59): the canonical spellings cash matching depends on.
        CheckConstraint(
            "contact_phone_snapshot IS NULL OR contact_phone_snapshot ~ '^\\+961[0-9]{7,8}$'",
            name="ck_orders_contact_phone_e164",
        ),
        CheckConstraint(
            f"contact_phone_hash IS NULL OR contact_phone_hash ~ '{PHONE_HASH_FORMAT}'",
            name="ck_orders_phone_hash_format",
        ),
        Index("ix_orders_user_placed", "user_id", text("placed_at DESC")),
        Index("ix_orders_status_placed", "status", text("placed_at DESC")),
        Index(
            "ix_orders_open_cash_phone",
            "contact_phone_hash",
            postgresql_where=text("payment_method = 'cash' AND status = 'in_progress'"),
        ),
        # VS-029 (b6e1d0c4a2f7): the admin "cash due" view and the queue, newest first.
        Index(
            "ix_orders_cash_due",
            text("placed_at DESC"),
            text("id DESC"),
            postgresql_where=text("payment_method = 'cash' AND status = 'in_progress'"),
        ),
        Index(
            "ix_orders_admin_queue",
            text("placed_at DESC"),
            text("id DESC"),
            postgresql_where=text(ADMIN_QUEUE_PREDICATE),
        ),
    )


class OrderItemModel(Base):
    """database-design.md 8.4; migration 03a4730dd046 (`offer_id` FK: 4b7e2c9d1f30)."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    offer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_type: Mapped[ProductType] = mapped_column(
        _pg_enum(ProductType, "product_type"), nullable=False
    )
    product_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    image_snapshot: Mapped[str | None] = mapped_column(Text)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    fulfillment_status: Mapped[OrderItemStatus] = mapped_column(
        _pg_enum(OrderItemStatus, "order_item_status"), nullable=False
    )
    lead_time_days_snapshot: Mapped[int | None] = mapped_column(Integer)
    batch_size_snapshot: Mapped[int | None] = mapped_column(Integer)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _pg_enum(PaymentMethod, "payment_method"), nullable=False
    )
    cancel_reason: Mapped[CancelReason | None] = mapped_column(
        _pg_enum(CancelReason, "cancel_reason")
    )
    receipt_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    problem_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_order_items_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        # VS-039 / ADR-034: a line's offer is its own customer's, on its own product.
        ForeignKeyConstraint(
            ["offer_id", "user_id", "product_id"],
            ["offers.id", "offers.user_id", "offers.product_id"],
            name="fk_order_items_offer_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        CheckConstraint(
            "offer_id IS NULL OR product_type = 'stl'", name="ck_order_items_offer_is_stl"
        ),
        # VS-041 / ADR-037: an offer pays for at most one line, ever.
        Index(
            "uq_order_items_offer_once",
            "offer_id",
            unique=True,
            postgresql_where=text("offer_id IS NOT NULL AND fulfillment_status <> 'cancelled'"),
        ),
        ForeignKeyConstraint(
            ["product_id", "product_type"],
            ["products.id", "products.type"],
            name="fk_order_items_product_type",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        CheckConstraint(
            "unit_price_cents >= 0 AND line_total_cents >= 0 AND quantity > 0 "
            "AND line_total_cents = unit_price_cents * quantity AND currency = 'USD'",
            name="ck_order_items_money",
        ),
        CheckConstraint(
            "product_type <> 'stl' OR quantity = 1", name="ck_order_items_stl_quantity_one"
        ),
        CheckConstraint(
            "payment_method <> 'cash' OR product_type = 'physical'",
            name="ck_order_items_cash_is_physical",
        ),
        CheckConstraint(
            "cancel_reason IS NULL OR fulfillment_status = 'cancelled'",
            name="ck_order_items_cancel_reason_state",
        ),
        CheckConstraint(
            "(product_type = 'physical' AND lead_time_days_snapshot IS NOT NULL "
            "AND batch_size_snapshot IS NOT NULL AND batch_size_snapshot > 0) "
            "OR (product_type = 'stl' AND lead_time_days_snapshot IS NULL "
            "AND batch_size_snapshot IS NULL)",
            name="ck_order_items_snapshots_by_type",
        ),
        CheckConstraint(
            "NOT (product_type = 'stl' AND fulfillment_status = 'delivered') "
            "OR (fulfilled_at IS NOT NULL AND delivered_by IS NOT NULL)",
            name="ck_order_items_stl_delivery_record",
        ),
        CheckConstraint(
            "product_type <> 'physical' OR delivered_by IS NULL",
            name="ck_order_items_physical_no_delivered_by",
        ),
        CheckConstraint(
            "(product_type = 'stl' AND fulfillment_status IN "
            "('pending', 'awaiting_delivery', 'delivered', 'refunded', 'cancelled')) "
            "OR (product_type = 'physical' AND fulfillment_status <> 'awaiting_delivery')",
            name="ck_order_items_status_by_type",
        ),
        Index("ix_order_items_order_id", "order_id"),
        Index(
            "ix_order_items_physical_status",
            "fulfillment_status",
            "order_id",
            postgresql_where=text("product_type = 'physical'"),
        ),
        Index(
            "ix_order_items_stl_awaiting",
            "created_at",
            "id",
            postgresql_where=text(
                "product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'"
            ),
        ),
        Index(
            "uq_order_items_stl_ownership",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text(
                "product_type = 'stl' "
                "AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')"
            ),
        ),
    )


class OrderStatusHistoryModel(Base):
    """database-design.md 8.5: append-only; `actor_user_id` NULL means the system."""

    __tablename__ = "order_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT")
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_order_status_history_order", "order_id", "created_at"),)


class CashPaymentBlockModel(Base):
    """database-design.md 8.6; migration fcd589e89e59. Holds only the phone's keyed hash;
    VS-031 inserts rows, VS-029 lists and clears them (cleared, never deleted)."""

    __tablename__ = "cash_payment_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_phone_hash: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Always 'cash' (plan Q4): the composite FK then refuses a block on an online order.
    order_payment_method: Mapped[PaymentMethod] = mapped_column(
        _pg_enum(PaymentMethod, "payment_method"), nullable=False, server_default=text("'cash'")
    )
    reason: Mapped[CancelReason] = mapped_column(
        _pg_enum(CancelReason, "cancel_reason"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleared_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_cash_payment_blocks_user", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["cleared_by"],
            ["users.id"],
            name="fk_cash_payment_blocks_cleared_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_id", "order_payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_cash_payment_blocks_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("order_id", name="uq_cash_payment_blocks_order"),
        CheckConstraint("reason IN ('refused', 'no_show')", name="ck_cash_payment_blocks_reason"),
        CheckConstraint("order_payment_method = 'cash'", name="ck_cash_payment_blocks_cash_only"),
        CheckConstraint(
            "(cleared_at IS NULL) = (cleared_by IS NULL)",
            name="ck_cash_payment_blocks_cleared_pair",
        ),
        CheckConstraint(
            f"contact_phone_hash ~ '{PHONE_HASH_FORMAT}'",
            name="ck_cash_payment_blocks_hash_format",
        ),
        Index(
            "ix_cash_payment_blocks_user_active",
            "user_id",
            postgresql_where=text("cleared_at IS NULL"),
        ),
        Index(
            "ix_cash_payment_blocks_phone_active",
            "contact_phone_hash",
            postgresql_where=text("cleared_at IS NULL"),
        ),
    )
