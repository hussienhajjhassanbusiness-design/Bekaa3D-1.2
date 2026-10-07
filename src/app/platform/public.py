"""Platform's published surface for other bounded contexts.

Another context may import from here or from `app.platform.application.ports`,
and from nowhere else in Platform (enforced by
`tests/unit/test_deep_architecture.py`). This module hands out the concrete
adapters; callers type against the ports.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.application.services.settings_reader import SettingsReader
from app.platform.infrastructure.audit_writer import SqlAuditWriter, SqlOutboxWriter
from app.platform.infrastructure.repositories import SettingRepository

__all__ = ["SettingsReader", "SqlAuditWriter", "SqlOutboxWriter", "settings_reader"]


def settings_reader(session: AsyncSession) -> SettingsReader:
    """Validated setting reads on the caller's session (and so its snapshot)."""
    return SettingsReader(SettingRepository(session))
