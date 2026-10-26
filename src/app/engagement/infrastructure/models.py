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
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engagement.domain.contact_message import (
    EMAIL_MAX,
    MESSAGE_MAX,
    NAME_MAX,
    PHONE_MAX,
    SUBJECT_MAX,
)
from app.engagement.domain.enums import (
    ContactMessageStatus,
    CustomRequestOutcome,
    CustomRequestStatus,
    NotificationType,
    UploadScanStatus,
)


class NotificationModel(Base):
    """database-design.md 12.3, exactly - six columns and no others.

    Notably absent, and absent on purpose: `updated_at` (every other table has
    one, but `read_at` is the only mutable field here), `deleted_at` (retention
    is explicitly "not numerically specified", so there is nothing to prune
    against yet), and any foreign key to an order/payment/offer. The payload is
    "supporting presentation data, not the source of truth for orders or
    payments", so a business-entity FK here would invite exactly the cross-
    context join the architecture forbids.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # CASCADE, unlike the SET NULL that `email_outbox` and `audit_logs` use.
    # Those two must outlive the account they refer to; a user's own unread
    # notifications must not. The choice is also forced rather than free:
    # `purge_unverified_accounts` issues a real physical DELETE against `users`,
    # and this column is NOT NULL, so SET NULL is not even representable - it
    # would make the purge job fail on a foreign-key violation the first time a
    # never-verified account had a notification.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            name="notification_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # NULL means unread. The whole read/unread model is this one column, which
    # is why the partial index below can be exactly the unread working set.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Both indexes come straight from database-design.md 12.3 and are not
        # widened here. `id` is not a member of either, even though the API
        # orders by `(created_at DESC, id DESC)` for a stable tie-break: the
        # leading columns are what make the scan selective, and adding a third
        # column to an approved index is a schema decision this slice does not
        # own.
        Index("ix_notifications_user_recent", "user_id", text("created_at DESC")),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("read_at IS NULL"),
        ),
    )


class ContactMessageModel(Base):
    """database-design.md 12.6; `user_id` and `order_id` set only by a problem report (VS-029b)."""

    __tablename__ = "contact_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT")
    )
    status: Mapped[ContactMessageStatus] = mapped_column(
        Enum(
            ContactMessageStatus,
            name="contact_message_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=ContactMessageStatus.NEW.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"char_length(name) <= {NAME_MAX} AND name ~ '[^[:space:]]'",
            name="ck_contact_messages_name_length",
        ),
        CheckConstraint(
            f"char_length(email) BETWEEN 3 AND {EMAIL_MAX} AND position('@' in email) > 1",
            name="ck_contact_messages_email_shape",
        ),
        CheckConstraint(
            f"phone IS NULL OR (char_length(phone) <= {PHONE_MAX} AND phone ~ '[^[:space:]]')",
            name="ck_contact_messages_phone_length",
        ),
        CheckConstraint(
            f"subject IS NULL OR (char_length(subject) <= {SUBJECT_MAX} "
            "AND subject ~ '[^[:space:]]')",
            name="ck_contact_messages_subject_length",
        ),
        CheckConstraint(
            f"char_length(message) <= {MESSAGE_MAX} AND message ~ '[^[:space:]]'",
            name="ck_contact_messages_message_length",
        ),
        # Queue order (VS-033 Q9): new first, oldest first; the enum sorts by declaration.
        Index("ix_contact_messages_queue", "status", "created_at", "id"),
        CheckConstraint(
            "order_id IS NULL OR user_id IS NOT NULL", name="ck_contact_messages_order_has_user"
        ),
        Index(
            "ix_contact_messages_order_id",
            "order_id",
            postgresql_where=text("order_id IS NOT NULL"),
        ),
        Index(
            "ix_contact_messages_user_id",
            "user_id",
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )


class WishlistItemModel(Base):
    """database-design.md 12.2. Soft delete; a removed row is never reused -
    re-adding inserts a fresh row (VS-038 plan §3)."""

    __tablename__ = "wishlist_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # CASCADE: same reasoning as notifications/addresses - moot in practice,
    # since only a verified user can ever write a row, but kept consistent.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: products are never hard-deleted (BR-018), same as product_images.
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # The load-bearing constraint: at most one active row per user and
        # product (CLAUDE.md - application checks lose races).
        Index(
            "uq_wishlist_items_user_product_live",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_wishlist_items_user_live",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_wishlist_items_product_live",
            "product_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class ReviewModel(Base):
    """database-design.md 12.1 (VS-036, ADR-044). Soft delete; moderation is `is_hidden`
    plus `hidden_at`, one fact under `ck_reviews_hidden_shape`."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # RESTRICT: reviews are history; only verified users write them, so the
    # unverified-account purge never meets one.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_reviews_user_id"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT", name="fk_reviews_product_id"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating_range"),
        CheckConstraint(
            "body IS NULL OR (btrim(body) <> '' AND char_length(body) <= 2000)",
            name="ck_reviews_body_shape",
        ),
        CheckConstraint("is_hidden = (hidden_at IS NOT NULL)", name="ck_reviews_hidden_shape"),
        CheckConstraint("updated_at >= created_at", name="ck_reviews_updated_after_created"),
        Index(
            "uq_reviews_user_product_live",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_reviews_product_visible",
            "product_id",
            text("created_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL AND NOT is_hidden"),
        ),
        Index(
            "ix_reviews_user_live",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


def _enum(enum: type[Any], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda members: [m.value for m in members])


class CustomRequestModel(Base):
    """database-design.md 12.4 without `user_id` (ADR-030); CHECKs live in 26d5d039d72c."""

    __tablename__ = "custom_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    project_title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_material: Mapped[str | None] = mapped_column(Text)
    preferred_colour: Mapped[str | None] = mapped_column(Text)
    dimensions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CustomRequestStatus] = mapped_column(
        _enum(CustomRequestStatus, "custom_request_status"),
        nullable=False,
        server_default=CustomRequestStatus.NEW.value,
    )
    quoted_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    outcome: Mapped[CustomRequestOutcome | None] = mapped_column(
        _enum(CustomRequestOutcome, "custom_request_outcome")
    )
    admin_notes: Mapped[str | None] = mapped_column(Text)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_custom_requests_queue", "status", "created_at", "id"),)


class CustomRequestAttachmentModel(Base):
    """database-design.md 12.5; hard-purged at `expires_at` (SRS 13.4)."""

    __tablename__ = "custom_request_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    custom_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("custom_requests.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    scan_status: Mapped[UploadScanStatus] = mapped_column(
        _enum(UploadScanStatus, "upload_scan_status"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_custom_request_attachments_storage_key"),
        Index("ix_custom_request_attachments_expires_at", "expires_at"),
        Index("ix_custom_request_attachments_request", "custom_request_id"),
    )
