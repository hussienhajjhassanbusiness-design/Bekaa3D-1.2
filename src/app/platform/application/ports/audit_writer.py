"""`AuditWriter`: the port other contexts use to append audit rows (VS-010)."""

from typing import Any, Protocol
from uuid import UUID


class AuditWriter(Protocol):
    """The sanctioned way for another context to append an audit record.

    Implementations write in the caller's transaction and never commit, so a
    business mutation and its audit row land together or not at all (BR-132).
    """

    async def record(
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
    ) -> None: ...
