"""offers and offer_rounds (VS-039, database-design.md 11), plus the `order_items.offer_id`
FK that 03a4730dd046 deferred. Revision ID: 4b7e2c9d1f30, revises 00ce1ce252a6."""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4b7e2c9d1f30"
down_revision: str | None = "00ce1ce252a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from the domain: a migration is frozen history.
_ENUMS: dict[str, tuple[str, ...]] = {
    "offer_status": (
        "awaiting_admin",
        "awaiting_customer",
        "accepted",
        "rejected",
        "expired",
        "withdrawn",
        "paid",
        "checkout_expired",
        "auto_closed",
    ),
    "offer_turn": ("admin", "customer"),
    "offer_actor": ("customer", "admin", "system"),
    "offer_action": (
        "submitted",
        "countered",
        "accepted",
        "rejected",
        "withdrawn",
        "expired",
        "paid",
        "checkout_expired",
        "auto_closed",
    ),
}
# Glossary "Live Offer" (SRS 11.4): the awaiting states and accepted.
_LIVE = "status IN ('awaiting_admin', 'awaiting_customer', 'accepted')"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def _moment(name: str, *, nullable: bool = True) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _now(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name in _ENUMS:
        postgresql.ENUM(*_ENUMS[name], name=name).create(bind)

    op.create_table(
        "offers",
        _uuid_pk(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("status", _enum("offer_status"), nullable=False),
        sa.Column("turn", _enum("offer_turn"), nullable=True),
        sa.Column("initial_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("current_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("agreed_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(3), server_default="USD", nullable=False),
        _moment("responds_by"),
        _moment("accepted_at"),
        _moment("checkout_expires_at"),
        _moment("rejected_at"),
        _moment("cooldown_until"),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "initial_amount_cents > 0 AND current_amount_cents > 0 "
            "AND (agreed_amount_cents IS NULL OR agreed_amount_cents > 0) AND currency = 'USD'",
            name="ck_offers_money",
        ),
        # SRS 11.2: a turn and a deadline exist exactly while a party must answer. NULL-safe
        # comparisons throughout: a CHECK that evaluates to NULL passes.
        sa.CheckConstraint(
            "(status = 'awaiting_admin' AND turn IS NOT DISTINCT FROM 'admin' "
            "AND responds_by IS NOT NULL) "
            "OR (status = 'awaiting_customer' AND turn IS NOT DISTINCT FROM 'customer' "
            "AND responds_by IS NOT NULL) "
            "OR (status NOT IN ('awaiting_admin', 'awaiting_customer') AND turn IS NULL)",
            name="ck_offers_turn_by_status",
        ),
        sa.CheckConstraint(
            "status <> 'accepted' OR (agreed_amount_cents IS NOT NULL "
            "AND accepted_at IS NOT NULL AND checkout_expires_at IS NOT NULL)",
            name="ck_offers_accepted_shape",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND cooldown_until IS NOT NULL)",
            name="ck_offers_rejected_shape",
        ),
    )
    # SRS 11.4: the race-safe guarantee of one live offer per (customer, product).
    op.create_index(
        "uq_offers_live",
        "offers",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text(_LIVE),
    )
    op.create_index("ix_offers_status_responds_by", "offers", ["status", "responds_by"])
    op.create_index(
        "ix_offers_user_created", "offers", ["user_id", sa.text("created_at DESC"), "id"]
    )
    op.create_index(
        "ix_offers_cooldown",
        "offers",
        ["user_id", "product_id", "cooldown_until"],
        postgresql_where=sa.text("status = 'rejected'"),
    )

    op.create_table(
        "offer_rounds",
        _uuid_pk(),
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("actor", _enum("offer_actor"), nullable=False),
        sa.Column("action", _enum("offer_action"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("offer_id", "sequence", name="uq_offer_rounds_offer_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_offer_rounds_sequence_positive"),
        sa.CheckConstraint(
            "(amount_cents IS NULL AND currency IS NULL) "
            "OR (amount_cents IS NOT NULL AND amount_cents > 0 "
            "AND currency IS NOT DISTINCT FROM 'USD')",
            name="ck_offer_rounds_money",
        ),
    )

    # NOT VALID, then VALIDATE: the scan runs under a lock that does not block writes.
    op.execute(
        "ALTER TABLE order_items ADD CONSTRAINT order_items_offer_id_fkey "
        "FOREIGN KEY (offer_id) REFERENCES offers (id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute("ALTER TABLE order_items VALIDATE CONSTRAINT order_items_offer_id_fkey")


def downgrade() -> None:
    # Dependents first: the order_items FK, then rounds, then offers, then the types.
    op.drop_constraint("order_items_offer_id_fkey", "order_items", type_="foreignkey")
    op.drop_table("offer_rounds")
    op.drop_table("offers")
    for name in reversed(list(_ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
