import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engagement.domain.enums import NotificationType


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
