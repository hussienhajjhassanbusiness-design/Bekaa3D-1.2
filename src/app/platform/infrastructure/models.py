import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.platform.domain.enums import OutboxStatus, SettingType


class EmailOutboxModel(Base):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    recipient_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(
            OutboxStatus, name="outbox_status", values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=False,
        server_default=OutboxStatus.PENDING.value,
    )
    send_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_email_outbox_due",
            "send_after",
            postgresql_where=text("status = 'pending'"),
        ),
        # database-design.md 13.3 specifies CHECK >= 0. attempt_count only ever
        # moves through mark_failed, but the count drives the retry backoff
        # exponent - a negative value would compute a nonsensical delay, and
        # that belongs in the database rather than in application trust.
        CheckConstraint("attempt_count >= 0", name="ck_email_outbox_attempt_count_non_negative"),
    )


class AuditLogModel(Base):
    """Monthly range-partitioned on `created_at` (ADR-015, VS-012a, migration
    c3d5e7f9a1b2). PostgreSQL requires the partition key in every unique
    constraint, hence the primary key `(id, created_at)`. Partitions are created
    by the migration and kept three months ahead by `app.jobs.partitions`; there
    is no DEFAULT partition, so an insert for an uncovered month fails loudly.

    `created_at` is part of the identity but has a server default; SQLAlchemy
    fetches server-generated primary-key columns back with RETURNING on insert,
    so a flushed row has its full identity (asserted by
    test_audit_logs_partitioning)."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    # clock_timestamp(), not now(): the insert time rather than the transaction
    # start, so the log's order matches the order changes happened (BUG-35).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_created_at_id", "created_at", "id"),
        Index("ix_audit_logs_actor_created_at", "actor_user_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        Index("ix_audit_logs_request_id", "request_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )


class SettingModel(Base):
    """database-design.md 13.1. A UUID primary key with a unique business key,
    matching the project-wide convention rather than keying on the text itself.

    What is deliberately *not* here: minimum, maximum, unit, nullability and
    public-ness. Those are validation rules, they live in the code registry, and
    storing them as columns would make widening a range something an
    administrator could do at runtime instead of something a reviewer approves.
    """

    __tablename__ = "settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[SettingType] = mapped_column(
        Enum(
            SettingType, name="setting_type", values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=False,
    )
    # `none_as_null=False` is the whole reason "optional" settings work. The
    # column is NOT NULL, but JSON has its own null, and an unconfigured pickup
    # address is stored as the JSON value `null` - a present document whose
    # content is null - rather than as SQL NULL. Left at the default this would
    # still behave correctly, but the distinction is too easy to misread to
    # leave implicit.
    value: Mapped[Any] = mapped_column(JSONB(none_as_null=False), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # SET NULL, matching audit_logs.actor_user_id: the record of *what* changed
    # must outlive the account that changed it.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
