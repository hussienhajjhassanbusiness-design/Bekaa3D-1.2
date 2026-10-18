"""Platform's published surface for other bounded contexts.

Another context may import from here or from `app.platform.application.ports`,
and from nowhere else in Platform (enforced by
`tests/unit/test_deep_architecture.py`). This module hands out the concrete
adapters; callers type against the ports.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.application.services.settings_reader import SettingsReader
from app.platform.domain.entities import IpHashSalt
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
from app.platform.infrastructure.repositories import SettingRepository, SqlIpHashSaltStore

__all__ = [
    "IDEMPOTENCY_TTL",
    "Claim",
    "Conflict",
    "InProgress",
    "IpHashSalt",
    "NewClaim",
    "Replay",
    "SettingsReader",
    "SqlAuditWriter",
    "SqlOutboxWriter",
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
