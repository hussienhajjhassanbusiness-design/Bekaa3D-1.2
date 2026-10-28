"""Platform's published surface for other bounded contexts.

Another context may import from here or from `app.platform.application.ports`,
and from nowhere else in Platform (enforced by
`tests/unit/test_deep_architecture.py`). This module hands out the concrete
adapters; callers type against the ports.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.application.services.settings_reader import SettingsReader
from app.platform.domain.entities import AuditLogEntry, IpHashSalt
from app.platform.domain.idempotency import (
    IDEMPOTENCY_TTL,
    Claim,
    Conflict,
    InProgress,
    NewClaim,
    Replay,
    request_hash,
)
from app.platform.infrastructure.audit_writer import SqlAuditWriter, SqlOutboxWriter
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from app.platform.infrastructure.repositories import (
    AuditLogRepository,
    EmailOutboxRepository,
    SettingRepository,
    SqlIpHashSaltStore,
)

__all__ = [
    "IDEMPOTENCY_TTL",
    "AuditLogEntry",
    "Claim",
    "Conflict",
    "InProgress",
    "IpHashSalt",
    "NewClaim",
    "Replay",
    "SettingsReader",
    "SqlAuditWriter",
    "SqlOutboxWriter",
    "anonymise_outbox",
    "audit_history",
    "current_ip_hash_salt",
    "idempotency_store",
    "ip_hash_salt_store",
    "request_hash",
    "settings_reader",
]


def settings_reader(session: AsyncSession) -> SettingsReader:
    """Validated setting reads on the caller's session (and so its snapshot)."""
    return SettingsReader(SettingRepository(session))


def ip_hash_salt_store(session: AsyncSession) -> SqlIpHashSaltStore:
    """The salt store on the caller's session, for the rotation job (VS-046)."""
    return SqlIpHashSaltStore(session)


async def current_ip_hash_salt(session: AsyncSession) -> IpHashSalt | None:
    """The current IP-hash salt, for the keyring in `app.core` (VS-046)."""
    return await SqlIpHashSaltStore(session).load_current()


def idempotency_store(session: AsyncSession) -> SqlIdempotencyStore:
    """Idempotency claims on the caller's session (VS-023; reused by VS-030)."""
    return SqlIdempotencyStore(session)


async def audit_history(
    session: AsyncSession, *, entity_type: str, entity_id: UUID, limit: int
) -> list[AuditLogEntry]:
    """One entity's audit rows, newest first (`ix_audit_logs_entity`); VS-024 detail."""
    return await AuditLogRepository(session).list_page(
        limit=limit, entity_type=entity_type, entity_id=entity_id
    )


async def anonymise_outbox(
    session: AsyncSession, user_id: UUID, *, email: str, at: datetime
) -> int:
    """VS-045: the account's outbox rows, for the deletion's transaction."""
    return await EmailOutboxRepository(session).anonymise_for_user(user_id, email=email, at=at)
