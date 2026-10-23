"""Refunds and chargebacks (VS-030 PR A, plan 4.2 and 4.2a): four tables, two enum types,
and the VS-041 audit Q-1 owner FK. Revision ID: c01e53ab3e0f, revises 0f43e238eaae."""

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c01e53ab3e0f"
down_revision: str | None = "0f43e238eaae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from the domain: a migration is frozen history.
_ENUMS: dict[str, tuple[str, ...]] = {
    "refund_kind": ("admin", "cancellation", "late_capture"),
    "refund_status": ("pending", "settled", "failed", "voided"),
}
_MISMATCHED_LINES = (
    "SELECT DISTINCT i.order_id FROM order_items i JOIN orders o ON o.id = i.order_id"
    " WHERE i.user_id <> o.user_id ORDER BY i.order_id"
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def _provider() -> postgresql.ENUM:
    return postgresql.ENUM(name="payment_provider", create_type=False)


def _moment(name: str, *, nullable: bool = True) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _now(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _user(name: str, *, nullable: bool = True) -> sa.Column[uuid.UUID]:
    return sa.Column(name, sa.UUID(), nullable=nullable)


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=f"fk_{table}_{column}", ondelete="RESTRICT"
    )


def _payment_fk(table: str) -> sa.ForeignKeyConstraint:
    """The payment is the order's, and `payment_provider` is its real provider."""
    return sa.ForeignKeyConstraint(
        ["payment_id", "order_id", "payment_provider"],
        ["payments.id", "payments.order_id", "payments.provider"],
        name=f"fk_{table}_payment",
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def _refuse_mismatched_lines() -> None:
    """Q-1 precheck: never auto-fix customer data; name order ids only, then roll back."""
    orders: list[uuid.UUID] = list(op.get_bind().execute(sa.text(_MISMATCHED_LINES)).scalars())
    if orders:
        sample = ", ".join(str(order_id) for order_id in orders[:20])
        raise RuntimeError(
            f"fk_order_items_order_owner: {len(orders)} order(s) have a line whose user_id"
            f" differs from the order's; fix them by hand first. Orders: {sample}"
        )


def upgrade() -> None:
    # Plan 4.2a: fail fast rather than queue behind live traffic; held until COMMIT.
    op.execute("SET LOCAL lock_timeout = '5s'")
    for name in _ENUMS:
        _enum(name).create(op.get_bind(), checkfirst=False)

    _refuse_mismatched_lines()
    # Composite keys the new FKs reference (each a superset of a primary key).
    op.create_unique_constraint("uq_orders_id_user", "orders", ["id", "user_id"])
    op.create_unique_constraint("uq_order_items_id_order", "order_items", ["id", "order_id"])
    op.create_unique_constraint(
        "uq_payments_id_order_provider", "payments", ["id", "order_id", "provider"]
    )
    # VS-041 audit Q-1: a line's customer is its order's. NOT VALID checks new rows at once,
    # then VALIDATE scans the existing ones under a lock that does not block writes.
    op.execute(
        "ALTER TABLE order_items ADD CONSTRAINT fk_order_items_order_owner "
        "FOREIGN KEY (order_id, user_id) REFERENCES orders (id, user_id) "
        "ON DELETE RESTRICT ON UPDATE RESTRICT NOT VALID"
    )
    op.execute("ALTER TABLE order_items VALIDATE CONSTRAINT fk_order_items_order_owner")

    _create_refunds()
    _create_items("refund_items", "refund_id", "refunds")
    _create_chargebacks()
    _create_items("chargeback_items", "chargeback_id", "chargebacks")


def _create_refunds() -> None:
    op.create_table(
        "refunds",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("payment_provider", _provider(), nullable=False),
        sa.Column("kind", _enum("refund_kind"), nullable=False),
        sa.Column("status", _enum("refund_status"), server_default="pending", nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _user("requested_by"),
        _user("approved_by"),
        sa.Column("reissue_of_refund_id", sa.UUID(), nullable=True),
        _moment("reissued_at"),
        _moment("settled_at"),
        _user("settled_by"),
        sa.Column("settlement_reference", sa.Text(), nullable=True),
        sa.Column("settlement_note", sa.Text(), nullable=True),
        _moment("failed_at"),
        _user("failed_by"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        _moment("voided_at"),
        _user("voided_by"),
        sa.Column("void_reason", sa.Text(), nullable=True),
        _moment("initiated_at", nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        _payment_fk("refunds"),
        sa.ForeignKeyConstraint(
            ["reissue_of_refund_id"],
            ["refunds.id"],
            name="fk_refunds_reissue_of_refund_id",
            ondelete="RESTRICT",
        ),
        *(
            _user_fk("refunds", column)
            for column in ("requested_by", "approved_by", "settled_by", "failed_by", "voided_by")
        ),
        sa.UniqueConstraint("id", "order_id", name="uq_refunds_id_order"),
        sa.UniqueConstraint("reissue_of_refund_id", name="uq_refunds_reissue_of"),
        sa.CheckConstraint("amount_cents > 0", name="ck_refunds_amount"),
        # Q6: only a late capture may carry the currency the provider reported.
        sa.CheckConstraint(
            "currency = 'USD' OR (kind = 'late_capture' AND currency ~ '^[A-Z]{3}$')",
            name="ck_refunds_currency",
        ),
        sa.CheckConstraint(
            "requested_by IS NOT NULL OR kind = 'late_capture'", name="ck_refunds_requester"
        ),
        sa.CheckConstraint(
            "kind <> 'late_capture' OR payment_provider <> 'cash'",
            name="ck_refunds_late_capture_online",
        ),
        # Also rules out a voided refund that was reissued (plan 4.2's void_not_reissued).
        sa.CheckConstraint(
            "reissued_at IS NULL OR status = 'failed'", name="ck_refunds_reissued_failed"
        ),
        sa.CheckConstraint(
            "(status <> 'settled' OR settled_at IS NOT NULL) "
            "AND (settled_at IS NULL OR status IN ('settled', 'voided')) "
            "AND (status <> 'failed' OR failed_at IS NOT NULL) "
            "AND (failed_at IS NULL OR status IN ('failed', 'voided')) "
            "AND ((status = 'voided') = (voided_at IS NOT NULL)) "
            "AND (voided_at IS NULL OR void_reason IS NOT NULL)",
            name="ck_refunds_state_stamps",
        ),
        sa.CheckConstraint(
            "NOT (status = 'voided' AND settled_at IS NOT NULL)",
            name="ck_refunds_void_never_settled",
        ),
        sa.CheckConstraint(
            "char_length(reason) BETWEEN 1 AND 1000 "
            "AND (settlement_reference IS NULL "
            "OR char_length(settlement_reference) BETWEEN 1 AND 200) "
            "AND (settlement_note IS NULL OR char_length(settlement_note) BETWEEN 1 AND 1000) "
            "AND (failure_reason IS NULL OR char_length(failure_reason) BETWEEN 1 AND 1000) "
            "AND (void_reason IS NULL OR char_length(void_reason) BETWEEN 1 AND 1000)",
            name="ck_refunds_text_lengths",
        ),
    )
    op.create_index(
        "uq_refunds_one_live_late_capture",
        "refunds",
        ["payment_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'late_capture' AND status NOT IN ('failed', 'voided')"),
    )
    # The obligations queue: pending and owed (failed, not reissued); database-design 19.9.
    op.create_index(
        "ix_refunds_obligations",
        "refunds",
        ["created_at", "id"],
        postgresql_where=sa.text(
            "status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)"
        ),
    )
    op.create_index("ix_refunds_order", "refunds", ["order_id", "created_at"])
    op.create_index("ix_refunds_payment", "refunds", ["payment_id"])


def _create_chargebacks() -> None:
    op.create_table(
        "chargebacks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("payment_provider", _provider(), nullable=False),
        sa.Column("provider_dispute_reference", sa.Text(), nullable=False),
        sa.Column("charged_cents", sa.BigInteger(), nullable=False),
        sa.Column("applied_cents", sa.BigInteger(), nullable=False),
        sa.Column("excess_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _user("recorded_by", nullable=False),
        _moment("received_at", nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id"),
        _payment_fk("chargebacks"),
        _user_fk("chargebacks", "recorded_by"),
        sa.UniqueConstraint("id", "order_id", name="uq_chargebacks_id_order"),
        sa.UniqueConstraint(
            "payment_provider", "provider_dispute_reference", name="uq_chargebacks_dispute"
        ),
        sa.CheckConstraint(
            "charged_cents > 0 AND applied_cents >= 0 AND excess_cents >= 0 "
            "AND applied_cents + excess_cents = charged_cents",
            name="ck_chargebacks_money",
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_chargebacks_currency"),
        sa.CheckConstraint("payment_provider <> 'cash'", name="ck_chargebacks_online_only"),
        sa.CheckConstraint(
            "char_length(provider_dispute_reference) BETWEEN 1 AND 200",
            name="ck_chargebacks_dispute_reference",
        ),
        sa.CheckConstraint("char_length(reason) BETWEEN 1 AND 1000", name="ck_chargebacks_reason"),
    )
    op.create_index("ix_chargebacks_order", "chargebacks", ["order_id", "created_at"])
    op.create_index("ix_chargebacks_payment", "chargebacks", ["payment_id"])


def _create_items(table: str, parent_column: str, parent: str) -> None:
    """`refund_items` / `chargeback_items`: each names a line of its parent's own order."""
    op.create_table(
        table,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(parent_column, sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            [parent_column, "order_id"],
            [f"{parent}.id", f"{parent}.order_id"],
            name=f"fk_{table}_{parent_column}",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id", "order_id"],
            ["order_items.id", "order_items.order_id"],
            name=f"fk_{table}_order_item",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.UniqueConstraint(parent_column, "order_item_id", name=f"uq_{table}_line"),
        sa.CheckConstraint("amount_cents > 0", name=f"ck_{table}_amount"),
    )
    op.create_index(f"ix_{table}_order_item", table, ["order_item_id"])


def downgrade() -> None:
    # Dependents first: the item tables, their parents, the owner FK, the keys, the types.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_table("chargeback_items")
    op.drop_table("refund_items")
    op.drop_table("chargebacks")
    op.drop_table("refunds")
    op.drop_constraint("fk_order_items_order_owner", "order_items", type_="foreignkey")
    op.drop_constraint("uq_payments_id_order_provider", "payments", type_="unique")
    op.drop_constraint("uq_order_items_id_order", "order_items", type_="unique")
    op.drop_constraint("uq_orders_id_user", "orders", type_="unique")
    for name in reversed(list(_ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
