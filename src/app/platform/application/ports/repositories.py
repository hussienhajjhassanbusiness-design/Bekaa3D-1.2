"""Platform's own repository ports (not for other contexts)."""

from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from app.platform.domain.entities import AuditLogEntry, Setting


class AuditLog(Protocol):
    """Platform writing its own `audit_logs` table (not for other contexts)."""

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
    ) -> AuditLogEntry: ...


class SettingStore(Protocol):
    async def get_by_key(self, key: str) -> Setting | None: ...

    async def get_by_key_for_update(self, key: str) -> Setting | None: ...

    async def get_many(self, keys: Sequence[str]) -> dict[str, Setting]: ...

    async def save(self, setting: Setting) -> None: ...
