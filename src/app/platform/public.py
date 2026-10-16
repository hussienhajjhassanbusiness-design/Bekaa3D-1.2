"""Platform's published surface for other bounded contexts.

Another context may import from here or from `app.platform.application.ports`,
and from nowhere else in Platform (enforced by
`tests/unit/test_deep_architecture.py`). This module hands out the concrete
adapters; callers type against the ports.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.application.services.settings_reader import SettingsReader
from app.platform.domain.entities import IpHashSalt
from app.platform.infrastructure.audit_writer import SqlAuditWriter, SqlOutboxWriter
from app.platform.infrastructure.repositories import SettingRepository, SqlIpHashSaltStore

__all__ = [
    "IpHashSalt",
    "SettingsReader",
    "SqlAuditWriter",
    "SqlOutboxWriter",
    "current_ip_hash_salt",
    "settings_reader",
]


def settings_reader(session: AsyncSession) -> SettingsReader:
    """Validated setting reads on the caller's session (and so its snapshot)."""
    return SettingsReader(SettingRepository(session))


async def current_ip_hash_salt(session: AsyncSession) -> IpHashSalt | None:
    """The current IP-hash salt, for the keyring in `app.core` (VS-046)."""
    return await SqlIpHashSaltStore(session).load_current()
