"""cash_payment_blocks, the three cash settings, free_shipping_threshold removed, and the
contact-phone format CHECKs (VS-028 PR A, ADR-024). Revision ID: fcd589e89e59, revises
d5507ee63176."""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fcd589e89e59"
down_revision: str | None = "d5507ee63176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from models: a migration is frozen history.
_settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    sa.column(
        "type",
        postgresql.ENUM(
            "boolean",
            "integer",
            "string",
            "money",
            "duration",
            "json",
            name="setting_type",
            create_type=False,
        ),
    ),
    sa.column("value", postgresql.JSONB(none_as_null=False)),
    sa.column("description", sa.Text),
)

# Written out literally, like de1d8a23512f: a later registry edit must not rewrite them.
_SEED: tuple[dict[str, Any], ...] = (
    {
        "key": "cash_payment_enabled",
        "type": "boolean",
        "value": True,
        "description": "Whether checkout offers cash on delivery or at pickup.",
    },
    {
        "key": "cash_max_open_orders",
        "type": "integer",
        "value": 1,
        "description": "Unpaid, uncancelled cash orders allowed per customer or contact phone.",
    },
    {
        "key": "cash_max_order_total",
        "type": "money",
        "value": {"amount_cents": 10_000, "currency": "USD"},
        "description": "Highest recomputed order total that may be paid in cash.",
    },
)
_KEYS = tuple(row["key"] for row in _SEED)
# Restored on downgrade exactly as de1d8a23512f seeded it.
_FREE_SHIPPING = {
    "key": "free_shipping_threshold",
    "type": "money",
    "value": None,
    "description": (
        "Order value at or above which delivery is free. JSON null disables free shipping."
    ),
}

_PAYMENT_METHOD = postgresql.ENUM("online", "cash", name="payment_method", create_type=False)
_CANCEL_REASON = postgresql.ENUM(
    "refused", "no_show", "other", name="cancel_reason", create_type=False
)
_HASH_FORMAT = "^[0-9a-f]{64}$"


def upgrade() -> None:
    op.create_table(
        "cash_payment_blocks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("contact_phone_hash", sa.Text(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        # Q4: always 'cash', so the composite FK below refuses a block on an online order.
        sa.Column(
            "order_payment_method",
            _PAYMENT_METHOD,
            server_default=sa.text("'cash'"),
            nullable=False,
        ),
        sa.Column("reason", _CANCEL_REASON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_cash_payment_blocks_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cleared_by"],
            ["users.id"],
            name="fk_cash_payment_blocks_cleared_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "order_payment_method"],
            ["orders.id", "orders.payment_method"],
            name="fk_cash_payment_blocks_order_payment_method",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.UniqueConstraint("order_id", name="uq_cash_payment_blocks_order"),
        sa.CheckConstraint(
            "reason IN ('refused', 'no_show')", name="ck_cash_payment_blocks_reason"
        ),
        sa.CheckConstraint(
            "order_payment_method = 'cash'", name="ck_cash_payment_blocks_cash_only"
        ),
        sa.CheckConstraint(
            "(cleared_at IS NULL) = (cleared_by IS NULL)",
            name="ck_cash_payment_blocks_cleared_pair",
        ),
        sa.CheckConstraint(
            f"contact_phone_hash ~ '{_HASH_FORMAT}'",
            name="ck_cash_payment_blocks_hash_format",
        ),
    )
    op.create_index(
        "ix_cash_payment_blocks_user_active",
        "cash_payment_blocks",
        ["user_id"],
        postgresql_where=sa.text("cleared_at IS NULL"),
    )
    op.create_index(
        "ix_cash_payment_blocks_phone_active",
        "cash_payment_blocks",
        ["contact_phone_hash"],
        postgresql_where=sa.text("cleared_at IS NULL"),
    )

    # No physical order exists yet, so both CHECKs validate against NULLs only.
    op.create_check_constraint(
        "ck_orders_contact_phone_e164",
        "orders",
        "contact_phone_snapshot IS NULL OR contact_phone_snapshot ~ '^\\+961[0-9]{7,8}$'",
    )
    op.create_check_constraint(
        "ck_orders_phone_hash_format",
        "orders",
        f"contact_phone_hash IS NULL OR contact_phone_hash ~ '{_HASH_FORMAT}'",
    )
    # The open-cash-order count by phone (plan Q3); by user it uses ix_orders_user_placed.
    op.create_index(
        "ix_orders_open_cash_phone",
        "orders",
        ["contact_phone_hash"],
        postgresql_where=sa.text("payment_method = 'cash' AND status = 'in_progress'"),
    )

    op.execute(
        postgresql.insert(_settings)
        .values(list(_SEED))
        .on_conflict_do_nothing(index_elements=["key"])
    )
    op.execute(_settings.delete().where(_settings.c.key == _FREE_SHIPPING["key"]))


def downgrade() -> None:
    op.execute(
        postgresql.insert(_settings)
        .values([_FREE_SHIPPING])
        .on_conflict_do_nothing(index_elements=["key"])
    )
    op.execute(_settings.delete().where(_settings.c.key.in_(_KEYS)))
    op.drop_index("ix_orders_open_cash_phone", table_name="orders")
    op.drop_constraint("ck_orders_phone_hash_format", "orders", type_="check")
    op.drop_constraint("ck_orders_contact_phone_e164", "orders", type_="check")
    op.drop_index("ix_cash_payment_blocks_phone_active", table_name="cash_payment_blocks")
    op.drop_index("ix_cash_payment_blocks_user_active", table_name="cash_payment_blocks")
    op.drop_table("cash_payment_blocks")
