"""orders, order_items, order_status_history, payments, webhook_events, idempotency_records
(VS-023 PR A): database-design.md 8.3-8.5, 9.1, 9.2, 13.4 with every frozen column.

Revision ID: 03a4730dd046, revises 26d5d039d72c."""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "03a4730dd046"
down_revision: str | None = "26d5d039d72c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from the domain: a migration is frozen history.
_ENUMS: dict[str, tuple[str, ...]] = {
    "fulfillment_method": ("delivery", "pickup"),
    "payment_method": ("online", "cash"),
    "cancel_reason": ("refused", "no_show", "other"),
    "order_source": ("cart", "offer"),
    "order_status": (
        "pending_payment",
        "cancelled",
        "refunded",
        "partially_refunded",
        "completed",
        "in_progress",
    ),
    "order_item_status": (
        "pending",
        "awaiting_delivery",
        "in_production",
        "ready_to_ship",
        "shipped",
        "delivered",
        "returned",
        "ready_for_pickup",
        "picked_up",
        "cancelled",
        "refunded",
    ),
    "payment_status": (
        "pending",
        "processing",
        "paid",
        "partially_refunded",
        "refunded",
        "failed",
        "expired",
    ),
    "payment_provider": ("mock", "cash"),
}


def _enum(name: str) -> postgresql.ENUM:
    # Created explicitly in upgrade(): several tables share these types.
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


# Owned by `products` (fc18b48a1780): reused here, never created or dropped.
_PRODUCT_TYPE = postgresql.ENUM("physical", "stl", name="product_type", create_type=False)


def _moment(name: str, *, nullable: bool = True) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name in _ENUMS:
        postgresql.ENUM(*_ENUMS[name], name=name).create(bind)

    op.create_table(
        "orders",
        _uuid_pk(),
        sa.Column("order_number", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("customer_email_snapshot", postgresql.CITEXT(), nullable=False),
        sa.Column("source", _enum("order_source"), nullable=False),
        sa.Column("status", _enum("order_status"), nullable=False),
        sa.Column("fulfillment_method", _enum("fulfillment_method"), nullable=True),
        sa.Column("payment_method", _enum("payment_method"), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        *[
            sa.Column(name, sa.Text(), nullable=True)
            for name in (
                "recipient_name",
                "contact_phone_snapshot",
                "contact_phone_hash",
                "governorate",
                "city",
                "area",
                "street",
                "landmark_notes",
                "customer_note",
                "admin_note",
            )
        ],
        _moment("estimated_dispatch_at"),
        _moment("terms_accepted_at", nullable=False),
        _moment("digital_terms_accepted_at"),
        # Plan addition (Q18, ADR-031): which digital-terms text was accepted.
        sa.Column("digital_terms_version", sa.Text(), nullable=True),
        _moment("cash_terms_accepted_at"),
        _moment("placed_at", nullable=False),
        _moment("completed_at"),
        _moment("cancelled_at"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        # The target of the composite FKs that copy payment_method (INV-21).
        sa.UniqueConstraint("id", "payment_method", name="uq_orders_id_payment_method"),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND total_cents >= 0", name="ck_orders_money_non_negative"
        ),
        sa.CheckConstraint("tax_cents = 0", name="ck_orders_tax_zero"),
        sa.CheckConstraint(
            "total_cents = subtotal_cents + tax_cents", name="ck_orders_total_arithmetic"
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_orders_currency_usd"),
        sa.CheckConstraint(
            "fulfillment_method IS NULL OR contact_phone_snapshot IS NOT NULL",
            name="ck_orders_physical_has_phone",
        ),
        sa.CheckConstraint(
            "fulfillment_method IS NOT NULL OR payment_method = 'online'",
            name="ck_orders_digital_only_online",
        ),
        sa.CheckConstraint(
            "payment_method <> 'cash' OR cash_terms_accepted_at IS NOT NULL",
            name="ck_orders_cash_terms",
        ),
        sa.CheckConstraint(
            "fulfillment_method IS DISTINCT FROM 'delivery' OR (recipient_name IS NOT NULL "
            "AND governorate IS NOT NULL AND city IS NOT NULL AND landmark_notes IS NOT NULL)",
            name="ck_orders_delivery_address",
        ),
        sa.CheckConstraint(
            "(contact_phone_snapshot IS NULL) = (contact_phone_hash IS NULL)",
            name="ck_orders_phone_hash_pair",
        ),
        sa.CheckConstraint(
            "(digital_terms_accepted_at IS NULL) = (digital_terms_version IS NULL)",
            name="ck_orders_digital_terms_version",
        ),
    )
    op.create_index("ix_orders_user_placed", "orders", ["user_id", sa.text("placed_at DESC")])
    op.create_index("ix_orders_status_placed", "orders", ["status", sa.text("placed_at DESC")])

    op.create_table(
        "order_items",
        _uuid_pk(),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        # No FK until `offers` exists (VS-039 adds it NOT VALID, then validates).
        sa.Column("offer_id", sa.UUID(), nullable=True),
        sa.Column("product_type", _PRODUCT_TYPE, nullable=False),
        sa.Column("product_name_snapshot", sa.Text(), nullable=False),
        sa.Column("image_snapshot", sa.Text(), nullable=True),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        sa.Column("fulfillment_status", _enum("order_item_status"), nullable=False),
        sa.Column("lead_time_days_snapshot", sa.Integer(), nullable=True),
        sa.Column("batch_size_snapshot", sa.Integer(), nullable=True),
        _moment("cancelled_at"),
        _moment("fulfilled_at"),
        sa.Column("delivered_by", sa.UUID(), nullable=True),
        sa.Column("payment_method", _enum("payment_method"), nullable=False),
        sa.Column("cancel_reason", _enum("cancel_reason"), nullable=True),
        _moment("receipt_confirmed_at"),
        _moment("problem_reported_at"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["order_id", "payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_order_items_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        # Proves the type snapshot, as cart_items does (ADR-029 d2).
        sa.ForeignKeyConstraint(
            ["product_id", "product_type"],
            ["products.id", "products.type"],
            name="fk_order_items_product_type",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["delivered_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "unit_price_cents >= 0 AND line_total_cents >= 0 AND quantity > 0 "
            "AND line_total_cents = unit_price_cents * quantity AND currency = 'USD'",
            name="ck_order_items_money",
        ),
        sa.CheckConstraint(
            "product_type <> 'stl' OR quantity = 1", name="ck_order_items_stl_quantity_one"
        ),
        sa.CheckConstraint(
            "payment_method <> 'cash' OR product_type = 'physical'",
            name="ck_order_items_cash_is_physical",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR fulfillment_status = 'cancelled'",
            name="ck_order_items_cancel_reason_state",
        ),
        sa.CheckConstraint(
            "(product_type = 'physical' AND lead_time_days_snapshot IS NOT NULL "
            "AND batch_size_snapshot IS NOT NULL AND batch_size_snapshot > 0) "
            "OR (product_type = 'stl' AND lead_time_days_snapshot IS NULL "
            "AND batch_size_snapshot IS NULL)",
            name="ck_order_items_snapshots_by_type",
        ),
        sa.CheckConstraint(
            "NOT (product_type = 'stl' AND fulfillment_status = 'delivered') "
            "OR (fulfilled_at IS NOT NULL AND delivered_by IS NOT NULL)",
            name="ck_order_items_stl_delivery_record",
        ),
        sa.CheckConstraint(
            "product_type <> 'physical' OR delivered_by IS NULL",
            name="ck_order_items_physical_no_delivered_by",
        ),
        # Plan addition: each type keeps to its own line states (3.7).
        sa.CheckConstraint(
            "(product_type = 'stl' AND fulfillment_status IN "
            "('pending', 'awaiting_delivery', 'delivered', 'refunded', 'cancelled')) "
            "OR (product_type = 'physical' AND fulfillment_status <> 'awaiting_delivery')",
            name="ck_order_items_status_by_type",
        ),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index(
        "ix_order_items_physical_status",
        "order_items",
        ["fulfillment_status", "order_id"],
        postgresql_where=sa.text("product_type = 'physical'"),
    )
    # INV-18, ADR-019 d5: one live STL line per customer and product.
    op.create_index(
        "uq_order_items_stl_ownership",
        "order_items",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text(
            "product_type = 'stl' "
            "AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')"
        ),
    )

    op.create_table(
        "order_status_history",
        _uuid_pk(),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=True),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_order_status_history_order", "order_status_history", ["order_id", "created_at"]
    )

    op.create_table(
        "payments",
        _uuid_pk(),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("provider", _enum("payment_provider"), nullable=False),
        sa.Column("order_payment_method", _enum("payment_method"), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("status", _enum("payment_status"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        _moment("initiated_at", nullable=False),
        _moment("verified_at"),
        _moment("late_captured_at"),
        _moment("failed_at"),
        _moment("expired_at"),
        sa.Column("provider_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("recorded_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["order_id", "order_payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_payments_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "provider", "provider_payment_id", name="uq_payments_provider_reference"
        ),
        sa.CheckConstraint(
            "amount_cents >= 0 AND currency = 'USD'", name="ck_payments_amount_currency"
        ),
        sa.CheckConstraint(
            "(provider = 'cash') = (order_payment_method = 'cash')",
            name="ck_payments_cash_iff_cash_order",
        ),
        sa.CheckConstraint(
            "provider <> 'cash' OR (status IN ('paid', 'partially_refunded', 'refunded') "
            "AND recorded_by IS NOT NULL AND verified_at IS NOT NULL AND amount_cents > 0)",
            name="ck_payments_cash_shape",
        ),
        sa.CheckConstraint(
            "late_captured_at IS NULL OR (status IN ('failed', 'expired') AND provider <> 'cash')",
            name="ck_payments_late_capture",
        ),
        sa.CheckConstraint(
            "provider = 'cash' OR recorded_by IS NULL", name="ck_payments_online_not_recorded"
        ),
        # Plan additions: "paid only through verification", in the database.
        sa.CheckConstraint(
            "status NOT IN ('paid', 'partially_refunded', 'refunded') OR verified_at IS NOT NULL",
            name="ck_payments_paid_verified",
        ),
        sa.CheckConstraint(
            "(status <> 'failed' OR failed_at IS NOT NULL) "
            "AND (status <> 'expired' OR expired_at IS NOT NULL)",
            name="ck_payments_terminal_timestamps",
        ),
    )
    # Created first, so a second cash payment reports INV-22 rather than one-live.
    op.create_index(
        "uq_payments_one_cash",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("provider = 'cash'"),
    )
    op.create_index(
        "uq_payments_one_live",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('failed', 'expired')"),
    )
    op.create_index("ix_payments_order", "payments", ["order_id"])
    op.create_index(
        "ix_payments_unsettled",
        "payments",
        ["status", "initiated_at"],
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )
    op.create_index(
        "ix_payments_late_captured",
        "payments",
        ["late_captured_at"],
        postgresql_where=sa.text("late_captured_at IS NOT NULL"),
    )

    op.create_table(
        "webhook_events",
        _uuid_pk(),
        sa.Column("provider", _enum("payment_provider"), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=True),
        # Plan additions (ADR-024 appendix): the payment link, resolved at receipt.
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _moment("processed_at"),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_webhook_events_provider_event"
        ),
        sa.CheckConstraint(
            "octet_length(payload::text) <= 65536", name="ck_webhook_events_payload_size"
        ),
    )
    op.create_index(
        "ix_webhook_events_unprocessed",
        "webhook_events",
        ["received_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index(
        "ix_webhook_events_payment_unprocessed",
        "webhook_events",
        ["payment_id"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )

    op.create_table(
        "idempotency_records",
        _uuid_pk(),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        # Plan additions: claim state and the resource it created (no FK: scope-generic).
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        _moment("expires_at", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "scope",
            "user_id",
            "key",
            name="uq_idempotency_records_scope_user_key",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 255", name="ck_idempotency_records_key_length"
        ),
        sa.CheckConstraint("state IN ('in_progress', 'done')", name="ck_idempotency_records_state"),
        sa.CheckConstraint(
            "(state = 'done') = (status_code IS NOT NULL AND response_body IS NOT NULL)",
            name="ck_idempotency_records_done_has_response",
        ),
        sa.CheckConstraint(
            "status_code IS NULL OR status_code BETWEEN 100 AND 599",
            name="ck_idempotency_records_status_code",
        ),
    )
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])


def downgrade() -> None:
    # Dependents first: webhook_events -> payments -> history -> order_items -> orders.
    op.drop_table("idempotency_records")
    op.drop_table("webhook_events")
    op.drop_table("payments")
    op.drop_table("order_status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
    for name in reversed(list(_ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
