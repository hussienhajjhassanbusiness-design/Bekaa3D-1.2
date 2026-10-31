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
from app.payments.domain.enums import PaymentProvider, PaymentStatus, RefundKind, RefundStatus

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
# Created by migration c01e53ab3e0f (VS-030).
_REFUND_KIND = Enum(
    RefundKind,
    name="refund_kind",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)
_REFUND_STATUS = Enum(
    RefundStatus,
    name="refund_status",
    create_type=False,
    values_callable=lambda e: [m.value for m in e],
)


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
        # VS-030 (c01e53ab3e0f): the key a refund's or chargeback's payment FK names.
        UniqueConstraint("id", "order_id", "provider", name="uq_payments_id_order_provider"),
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
        # VS-050 (941b40d285ce): nothing can report a `manual` attempt as in progress.
        CheckConstraint(
            "provider <> 'manual' OR status <> 'processing'",
            name="ck_payments_manual_never_processing",
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
        Index(  # the admin work list (ADR-049 d11)
            "ix_payments_awaiting_manual",
            "initiated_at",
            "id",
            postgresql_where=text("provider = 'manual' AND status = 'pending'"),
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


def _user_fk(table: str, column: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        [column], ["users.id"], name=f"fk_{table}_{column}", ondelete="RESTRICT"
    )


def _payment_fk(table: str) -> ForeignKeyConstraint:
    """The payment is the order's, and `payment_provider` is its real provider."""
    return ForeignKeyConstraint(
        ["payment_id", "order_id", "payment_provider"],
        ["payments.id", "payments.order_id", "payments.provider"],
        name=f"fk_{table}_payment",
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def _item_fks(table: str, parent_column: str, parent: str) -> tuple[ForeignKeyConstraint, ...]:
    """An item names a line of its parent's own order (plan 4.2 steps 6 and 8)."""
    return (
        ForeignKeyConstraint(
            [parent_column, "order_id"],
            [f"{parent}.id", f"{parent}.order_id"],
            name=f"fk_{table}_{parent_column}",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_item_id", "order_id"],
            ["order_items.id", "order_items.order_id"],
            name=f"fk_{table}_order_item",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )


class RefundModel(Base):
    """database-design.md 9.3; migration c01e53ab3e0f (VS-030, ADR-042)."""

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payment_provider: Mapped[PaymentProvider] = mapped_column(_PROVIDER, nullable=False)
    kind: Mapped[RefundKind] = mapped_column(_REFUND_KIND, nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        _REFUND_STATUS, nullable=False, server_default="pending"
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reissue_of_refund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reissued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    settlement_reference: Mapped[str | None] = mapped_column(Text)
    settlement_note: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        _payment_fk("refunds"),
        ForeignKeyConstraint(
            ["reissue_of_refund_id"],
            ["refunds.id"],
            name="fk_refunds_reissue_of_refund_id",
            ondelete="RESTRICT",
        ),
        *(
            _user_fk("refunds", column)
            for column in ("requested_by", "approved_by", "settled_by", "failed_by", "voided_by")
        ),
        UniqueConstraint("id", "order_id", name="uq_refunds_id_order"),
        UniqueConstraint("reissue_of_refund_id", name="uq_refunds_reissue_of"),
        CheckConstraint("amount_cents > 0", name="ck_refunds_amount"),
        CheckConstraint(
            "currency = 'USD' OR (kind = 'late_capture' AND currency ~ '^[A-Z]{3}$')",
            name="ck_refunds_currency",
        ),
        CheckConstraint(
            "requested_by IS NOT NULL OR kind = 'late_capture'", name="ck_refunds_requester"
        ),
        CheckConstraint(
            "kind <> 'late_capture' OR payment_provider <> 'cash'",
            name="ck_refunds_late_capture_online",
        ),
        CheckConstraint(
            "reissued_at IS NULL OR status = 'failed'", name="ck_refunds_reissued_failed"
        ),
        CheckConstraint(
            "(status <> 'settled' OR settled_at IS NOT NULL) "
            "AND (settled_at IS NULL OR status IN ('settled', 'voided')) "
            "AND (status <> 'failed' OR failed_at IS NOT NULL) "
            "AND (failed_at IS NULL OR status IN ('failed', 'voided')) "
            "AND ((status = 'voided') = (voided_at IS NOT NULL)) "
            "AND (voided_at IS NULL OR void_reason IS NOT NULL)",
            name="ck_refunds_state_stamps",
        ),
        CheckConstraint(
            "NOT (status = 'voided' AND settled_at IS NOT NULL)",
            name="ck_refunds_void_never_settled",
        ),
        CheckConstraint(
            "char_length(reason) BETWEEN 1 AND 1000 "
            "AND (settlement_reference IS NULL "
            "OR char_length(settlement_reference) BETWEEN 1 AND 200) "
            "AND (settlement_note IS NULL OR char_length(settlement_note) BETWEEN 1 AND 1000) "
            "AND (failure_reason IS NULL OR char_length(failure_reason) BETWEEN 1 AND 1000) "
            "AND (void_reason IS NULL OR char_length(void_reason) BETWEEN 1 AND 1000)",
            name="ck_refunds_text_lengths",
        ),
        Index(
            "uq_refunds_one_live_late_capture",
            "payment_id",
            unique=True,
            postgresql_where=text("kind = 'late_capture' AND status NOT IN ('failed', 'voided')"),
        ),
        Index(
            "ix_refunds_obligations",
            "created_at",
            "id",
            postgresql_where=text(
                "status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)"
            ),
        ),
        Index("ix_refunds_order", "order_id", "created_at"),
        Index("ix_refunds_payment", "payment_id"),
    )


class RefundItemModel(Base):
    """database-design.md 9.4; migration c01e53ab3e0f (VS-030)."""

    __tablename__ = "refund_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    refund_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        *_item_fks("refund_items", "refund_id", "refunds"),
        UniqueConstraint("refund_id", "order_item_id", name="uq_refund_items_line"),
        CheckConstraint("amount_cents > 0", name="ck_refund_items_amount"),
        Index("ix_refund_items_order_item", "order_item_id"),
    )


class ChargebackModel(Base):
    """database-design.md 9.5; migration c01e53ab3e0f (VS-030; ADR-042: not a refund kind)."""

    __tablename__ = "chargebacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payment_provider: Mapped[PaymentProvider] = mapped_column(_PROVIDER, nullable=False)
    provider_dispute_reference: Mapped[str] = mapped_column(Text, nullable=False)
    charged_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    applied_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    excess_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        _payment_fk("chargebacks"),
        _user_fk("chargebacks", "recorded_by"),
        UniqueConstraint("id", "order_id", name="uq_chargebacks_id_order"),
        UniqueConstraint(
            "payment_provider", "provider_dispute_reference", name="uq_chargebacks_dispute"
        ),
        CheckConstraint(
            "charged_cents > 0 AND applied_cents >= 0 AND excess_cents >= 0 "
            "AND applied_cents + excess_cents = charged_cents",
            name="ck_chargebacks_money",
        ),
        CheckConstraint("currency = 'USD'", name="ck_chargebacks_currency"),
        CheckConstraint("payment_provider <> 'cash'", name="ck_chargebacks_online_only"),
        CheckConstraint(
            "char_length(provider_dispute_reference) BETWEEN 1 AND 200",
            name="ck_chargebacks_dispute_reference",
        ),
        CheckConstraint("char_length(reason) BETWEEN 1 AND 1000", name="ck_chargebacks_reason"),
        Index("ix_chargebacks_order", "order_id", "created_at"),
        Index("ix_chargebacks_payment", "payment_id"),
    )


class ChargebackItemModel(Base):
    """database-design.md 9.6; migration c01e53ab3e0f (VS-030)."""

    __tablename__ = "chargeback_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    chargeback_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        *_item_fks("chargeback_items", "chargeback_id", "chargebacks"),
        UniqueConstraint("chargeback_id", "order_item_id", name="uq_chargeback_items_line"),
        CheckConstraint("amount_cents > 0", name="ck_chargeback_items_amount"),
        Index("ix_chargeback_items_order_item", "order_item_id"),
    )
