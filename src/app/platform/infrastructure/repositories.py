from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.entities import AuditLogEntry, EmailOutboxMessage, IpHashSalt, Setting
from app.platform.domain.enums import OutboxStatus, SettingType
from app.platform.infrastructure.models import (
    AuditLogModel,
    EmailOutboxModel,
    IpHashSaltModel,
    SettingModel,
)


def _outbox_to_domain(model: EmailOutboxModel) -> EmailOutboxMessage:
    return EmailOutboxMessage(
        id=model.id,
        user_id=model.user_id,
        recipient_email=str(model.recipient_email),
        template=model.template,
        payload=model.payload,
        status=model.status,
        send_after=model.send_after,
        attempt_count=model.attempt_count,
        last_error=model.last_error,
        sent_at=model.sent_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class EmailOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: UUID | None,
        recipient_email: str,
        template: str,
        payload: dict[str, Any],
    ) -> EmailOutboxMessage:
        model = EmailOutboxModel(
            user_id=user_id,
            recipient_email=recipient_email,
            template=template,
            payload=payload,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _outbox_to_domain(model)

    async def claim_due(self, *, limit: int, now: datetime) -> list[EmailOutboxMessage]:
        """Locks up to `limit` due pending rows for this transaction only, so
        concurrent workers never process the same message (SRS: outbox rows must
        not be delivered twice by concurrent workers)."""
        stmt = (
            select(EmailOutboxModel)
            .where(
                EmailOutboxModel.status == OutboxStatus.PENDING,
                EmailOutboxModel.send_after <= now,
            )
            .order_by(EmailOutboxModel.send_after)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = (await self._session.scalars(stmt)).all()
        return [_outbox_to_domain(model) for model in models]

    async def save(self, message: EmailOutboxMessage) -> None:
        model = await self._session.get(EmailOutboxModel, message.id)
        if model is None:
            raise ValueError(f"EmailOutboxMessage {message.id} not found")
        model.status = message.status
        # payload is written back because reaching a terminal state redacts it
        model.payload = message.payload
        model.send_after = message.send_after
        model.attempt_count = message.attempt_count
        model.last_error = message.last_error
        model.sent_at = message.sent_at
        await self._session.flush()


def _audit_to_domain(model: AuditLogModel) -> AuditLogEntry:
    return AuditLogEntry(
        id=model.id,
        actor_user_id=model.actor_user_id,
        action=model.action,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        before_data=model.before_data,
        after_data=model.after_data,
        request_id=model.request_id,
        ip_hash=model.ip_hash,
        created_at=model.created_at,
    )


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_hash: str | None = None,
    ) -> AuditLogEntry:
        model = AuditLogModel(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _audit_to_domain(model)

    async def get_by_id(self, audit_id: UUID) -> AuditLogEntry | None:
        """By `id` alone: the primary key is `(id, created_at)` since VS-012a, so
        this probes each partition's key index rather than pruning to one. With
        one partition a month that is a handful of index lookups."""
        model = await self._session.scalar(
            select(AuditLogModel).where(AuditLogModel.id == audit_id)
        )
        return _audit_to_domain(model) if model is not None else None

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None = None,
        actor_user_id: UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        request_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[AuditLogEntry]:
        """One page, newest first: `(created_at, id)` descending.

        `created_at` is not unique, so `id` breaks ties, and the cursor is the
        pair - compared as a row value so it walks `ix_audit_logs_created_at_id`
        backwards, merged across partitions, instead of sorting. The date range
        is half-open, `[created_after, created_before)`, which also lets the
        planner prune partitions outside it.

        Every filter is an equality or range on a bound parameter; nothing a
        client sends is ever interpolated into SQL.
        """
        stmt = (
            select(AuditLogModel)
            .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(tuple_(AuditLogModel.created_at, AuditLogModel.id) < after)
        if actor_user_id is not None:
            stmt = stmt.where(AuditLogModel.actor_user_id == actor_user_id)
        if action is not None:
            stmt = stmt.where(AuditLogModel.action == action)
        if entity_type is not None:
            stmt = stmt.where(AuditLogModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLogModel.entity_id == entity_id)
        if request_id is not None:
            stmt = stmt.where(AuditLogModel.request_id == request_id)
        if created_after is not None:
            stmt = stmt.where(AuditLogModel.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(AuditLogModel.created_at < created_before)
        models = (await self._session.scalars(stmt)).all()
        return [_audit_to_domain(model) for model in models]


# Distinct from ENSURE_PARTITIONS_LOCK_KEY and the last-administrator lock.
IP_HASH_ROTATION_LOCK_KEY = 0x62656B6149505348  # "bekaIPSH"


class SqlIpHashSaltStore:
    """The `ip_hash_salts` table (VS-046, ADR-028). Salt bytes are only ever read here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_rotation(self) -> None:
        """Serialise rotations for the rest of the caller's transaction."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": IP_HASH_ROTATION_LOCK_KEY}
        )

    async def current_created_at(self) -> tuple[UUID, datetime] | None:
        """The current salt's id and age; never selects the bytes."""
        row = (
            await self._session.execute(
                select(IpHashSaltModel.id, IpHashSaltModel.created_at).where(
                    IpHashSaltModel.is_current
                )
            )
        ).one_or_none()
        return (row.id, row.created_at) if row else None

    async def replace_current(self) -> UUID:
        """Delete every salt and insert one generated by pgcrypto (grace 0, ADR-028)."""
        await self._session.execute(delete(IpHashSaltModel))
        new_id: UUID = await self._session.scalar(
            text("INSERT INTO ip_hash_salts (salt) VALUES (gen_random_bytes(32)) RETURNING id")
        )
        return new_id

    async def load_current(self) -> IpHashSalt | None:
        row = (
            await self._session.execute(
                select(IpHashSaltModel.id, IpHashSaltModel.created_at, IpHashSaltModel.salt).where(
                    IpHashSaltModel.is_current
                )
            )
        ).one_or_none()
        return IpHashSalt(id=row.id, created_at=row.created_at, salt=row.salt) if row else None


def _setting_to_domain(model: SettingModel) -> Setting:
    return Setting(
        id=model.id,
        key=model.key,
        type=model.type,
        value=model.value,
        description=model.description,
        updated_by=model.updated_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> Setting | None:
        """Unlocked read, for consumers that only need the current value."""
        stmt = select(SettingModel).where(SettingModel.key == key)
        model = await self._session.scalar(stmt)
        return _setting_to_domain(model) if model else None

    async def get_by_key_for_update(self, key: str) -> Setting | None:
        """Read one setting and hold a row lock until the transaction ends.

        This is what serialises two administrators editing the same key. The
        second blocks here, then re-reads the row the first one committed, so
        its audit entry records the value it genuinely replaced instead of a
        stale one (FR-18: "deterministic ... last-commit behavior with both
        attempts audited").

        `populate_existing` matters for the same reason it did on the MFA
        credential and the user row: without it SQLAlchemy returns the instance
        already in this session's identity map, and the post-lock read would
        hand back pre-lock data - which is precisely the value the lock exists
        to invalidate.
        """
        stmt = (
            select(SettingModel)
            .where(SettingModel.key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _setting_to_domain(model) if model else None

    async def get_many(self, keys: Sequence[str]) -> dict[str, Setting]:
        """The settings for an explicit list of keys, indexed by key.

        Used by the public endpoint, which passes the allowlist. Reading only
        the named keys - rather than reading everything and filtering in Python
        - means a setting that is not on the allowlist never leaves the
        database, so a filtering mistake cannot become a disclosure.
        """
        if not keys:
            return {}
        stmt = select(SettingModel).where(SettingModel.key.in_(keys))
        models = (await self._session.scalars(stmt)).all()
        return {model.key: _setting_to_domain(model) for model in models}

    async def list_page(
        self,
        *,
        limit: int,
        after_key: str | None = None,
        prefix: str | None = None,
        setting_type: SettingType | None = None,
    ) -> list[Setting]:
        """One page of settings, ordered by key.

        `key` is unique, so it is a complete sort order on its own and doubles
        as the cursor - no separate tie-breaker is needed here, unlike the
        `created_at` orderings elsewhere in the API (api-endpoints.md 2.2).

        The caller asks for `limit + 1` rows to discover whether a further page
        exists, which is why this returns a plain list and does no counting: a
        `COUNT(*)` would be a second query to answer a question the extra row
        already answers.
        """
        stmt = select(SettingModel).order_by(SettingModel.key.asc()).limit(limit)
        if after_key is not None:
            stmt = stmt.where(SettingModel.key > after_key)
        if prefix:
            # autoescape, or a prefix containing % or _ would be read as a LIKE
            # wildcard and quietly match the wrong rows.
            stmt = stmt.where(SettingModel.key.startswith(prefix, autoescape=True))
        if setting_type is not None:
            stmt = stmt.where(SettingModel.type == setting_type)
        models = (await self._session.scalars(stmt)).all()
        return [_setting_to_domain(model) for model in models]

    async def save(self, setting: Setting) -> None:
        """Persist a changed value.

        `key`, `type` and `description` are absent on purpose: the key and its
        declared type are schema-defined and the API cannot change them, and the
        description belongs to the registry that the seed migration wrote.
        """
        model = await self._session.get(SettingModel, setting.id)
        if model is None:
            raise ValueError(f"Setting {setting.id} not found")
        model.value = setting.value
        model.updated_by = setting.updated_by
        model.updated_at = setting.updated_at
        await self._session.flush()
