"""`IdempotencyStore`: the port checkout (VS-023) and refunds (VS-030) claim keys through."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.platform.domain.idempotency import Claim


class IdempotencyStore(Protocol):
    """Runs in the caller's transaction and never commits."""

    async def claim(
        self,
        *,
        scope: str,
        user_id: UUID | None,
        key: str,
        request_hash: str,
        expires_at: datetime,
    ) -> Claim:
        """Insert an `in_progress` claim, or report what an existing one holds. A rival
        insert of the same key waits for that transaction to end first."""
        ...

    async def attach(self, record_id: UUID, *, resource_id: UUID) -> None: ...

    async def complete(self, record_id: UUID, *, status_code: int, body: dict[str, Any]) -> None:
        """Store the final response; the claim becomes `done`."""
        ...

    async def purge_expired(self, *, now: datetime, limit: int) -> int:
        """Delete up to `limit` expired claims, skipping locked ones."""
        ...
