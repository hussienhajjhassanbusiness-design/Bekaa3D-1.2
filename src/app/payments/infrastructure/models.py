import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.payments.domain.enums import PaymentProvider, PaymentStatus

# Types created by migration 03a4730dd046, never by the ORM. `payment_method` belongs
# to Ordering, so it is named here by value rather than imported across contexts.
_PROVIDER = Enum(
    PaymentProvider,
    name="payment_provider",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_STATUS = Enum(
    PaymentStatus,
    name="payment_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_ORDER_PAYMENT_METHOD = Enum("online", "cash", name="payment_method", create_type=False)


class PaymentModel(Base):
    """database-design.md 9.1; migration 03a4730dd046."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(_PROVIDER, nullable=False)
    order_payment_method: Mapped[str] = mapped_column(_ORDER_PAYMENT_METHOD, nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PaymentStatus] = mapped_column(_STATUS, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # VS-024 (migration 00ce1ce252a6): what the provider reported captured.
    captured_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    captured_currency: Mapped[str | None] = mapped_column(CHAR(3))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "order_payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_payments_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_reference"),
        CheckConstraint(
            "amount_cents >= 0 AND currency = 'USD'", name="ck_payments_amount_currency"
        ),
        CheckConstraint(
            "(provider = 'cash') = (order_payment_method = 'cash')",
            name="ck_payments_cash_iff_cash_order",
        ),
        CheckConstraint(
            "provider <> 'cash' OR (status IN ('paid', 'partially_refunded', 'refunded') "
            "AND recorded_by IS NOT NULL AND verified_at IS NOT NULL AND amount_cents > 0)",
            name="ck_payments_cash_shape",
        ),
        CheckConstraint(
            "late_captured_at IS NULL OR (status IN ('failed', 'expired') AND provider <> 'cash')",
            name="ck_payments_late_capture",
        ),
        CheckConstraint(
            "provider = 'cash' OR recorded_by IS NULL", name="ck_payments_online_not_recorded"
        ),
        CheckConstraint(
            "status NOT IN ('paid', 'partially_refunded', 'refunded') OR verified_at IS NOT NULL",
            name="ck_payments_paid_verified",
        ),
        CheckConstraint(
            "(status <> 'failed' OR failed_at IS NOT NULL) "
            "AND (status <> 'expired' OR expired_at IS NOT NULL)",
            name="ck_payments_terminal_timestamps",
        ),
        CheckConstraint(
            "(captured_amount_cents IS NULL OR captured_amount_cents >= 0) "
            "AND (captured_currency IS NULL OR captured_currency ~ '^[A-Z]{3}$') "
            "AND (captured_currency IS NULL OR captured_amount_cents IS NOT NULL)",
            name="ck_payments_captured_shape",
        ),
        CheckConstraint(
            "captured_amount_cents IS NULL OR (provider <> 'cash' AND "
            "(late_captured_at IS NOT NULL "
            "OR status IN ('paid', 'partially_refunded', 'refunded')))",
            name="ck_payments_captured_when",
        ),
        Index(
            "uq_payments_one_live",
            "order_id",
            unique=True,
            postgresql_where=text("status NOT IN ('failed', 'expired')"),
        ),
        Index(
            "uq_payments_one_cash",
            "order_id",
            unique=True,
            postgresql_where=text("provider = 'cash'"),
        ),
        Index("ix_payments_order", "order_id"),
        Index(
            "ix_payments_unsettled",
            "status",
            "initiated_at",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        Index(
            "ix_payments_late_captured",
            "late_captured_at",
            postgresql_where=text("late_captured_at IS NOT NULL"),
        ),
    )


class WebhookEventModel(Base):
    """database-design.md 9.2 plus the payment link resolved at receipt (VS-023 plan 4.6)."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider: Mapped[PaymentProvider] = mapped_column(_PROVIDER, nullable=False)
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature_valid: Mapped[bool | None] = mapped_column(Boolean)
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_events_provider_event"),
        CheckConstraint(
            "octet_length(payload::text) <= 65536", name="ck_webhook_events_payload_size"
        ),
        Index(
            "ix_webhook_events_unprocessed",
            "received_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
        Index(
            "ix_webhook_events_payment_unprocessed",
            "payment_id",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )
