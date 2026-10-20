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
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.negotiation.domain.enums import OfferAction, OfferActor, OfferStatus, OfferTurn

# Mirrors the migration's CHECKs (its constants are frozen history; these are the model's).
LIVE_SQL = "status IN ('awaiting_admin', 'awaiting_customer', 'accepted')"


def _pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """A PostgreSQL type created by a migration, never by the ORM."""
    return Enum(enum, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])


class OfferModel(Base):
    """database-design.md 11.1; migrations 4b7e2c9d1f30 (VS-039), 8d2f6a1c3e57."""

    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[OfferStatus] = mapped_column(
        _pg_enum(OfferStatus, "offer_status"), nullable=False
    )
    turn: Mapped[OfferTurn | None] = mapped_column(_pg_enum(OfferTurn, "offer_turn"))
    initial_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agreed_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    responds_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkout_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("id", "user_id", "product_id", name="uq_offers_id_user_product"),
        CheckConstraint(
            "initial_amount_cents > 0 AND current_amount_cents > 0 "
            "AND (agreed_amount_cents IS NULL OR agreed_amount_cents > 0) AND currency = 'USD'",
            name="ck_offers_money",
        ),
        CheckConstraint(
            "(status = 'awaiting_admin' AND turn IS NOT DISTINCT FROM 'admin' "
            "AND responds_by IS NOT NULL) "
            "OR (status = 'awaiting_customer' AND turn IS NOT DISTINCT FROM 'customer' "
            "AND responds_by IS NOT NULL) "
            "OR (status NOT IN ('awaiting_admin', 'awaiting_customer') AND turn IS NULL)",
            name="ck_offers_turn_by_status",
        ),
        CheckConstraint(
            "status NOT IN ('accepted', 'paid', 'checkout_expired') "
            "OR (agreed_amount_cents IS NOT NULL AND accepted_at IS NOT NULL "
            "AND checkout_expires_at IS NOT NULL)",
            name="ck_offers_accepted_shape",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND cooldown_until IS NOT NULL)",
            name="ck_offers_rejected_shape",
        ),
        CheckConstraint(
            "remind_at IS NULL OR status = 'awaiting_customer'",
            name="ck_offers_remind_at_awaiting_customer",
        ),
        CheckConstraint(
            "agreed_amount_cents IS NULL OR agreed_amount_cents <= current_amount_cents",
            name="ck_offers_agreed_within_current",
        ),
        Index(
            "uq_offers_live",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text(LIVE_SQL),
        ),
        Index("ix_offers_status_responds_by", "status", "responds_by"),
        Index("ix_offers_user_created", "user_id", text("created_at DESC"), "id"),
        Index(
            "ix_offers_cooldown",
            "user_id",
            "product_id",
            "cooldown_until",
            postgresql_where=text("status = 'rejected'"),
        ),
        Index("ix_offers_remind_at", "remind_at", postgresql_where=text("remind_at IS NOT NULL")),
    )


class OfferRoundModel(Base):
    """database-design.md 11.2: append-only; nothing in the code updates or deletes a row."""

    __tablename__ = "offer_rounds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[OfferActor] = mapped_column(_pg_enum(OfferActor, "offer_actor"), nullable=False)
    action: Mapped[OfferAction] = mapped_column(
        _pg_enum(OfferAction, "offer_action"), nullable=False
    )
    amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("offer_id", "sequence", name="uq_offer_rounds_offer_sequence"),
        CheckConstraint("sequence > 0", name="ck_offer_rounds_sequence_positive"),
        CheckConstraint(
            "(amount_cents IS NULL AND currency IS NULL) "
            "OR (amount_cents IS NOT NULL AND amount_cents > 0 "
            "AND currency IS NOT DISTINCT FROM 'USD')",
            name="ck_offer_rounds_money",
        ),
    )
