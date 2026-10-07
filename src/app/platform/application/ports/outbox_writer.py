"""`OutboxWriter`: the port other contexts use to queue transactional email."""

from typing import Any, Protocol
from uuid import UUID

from app.platform.domain.entities import EmailOutboxMessage


class OutboxWriter(Protocol):
    """Queue an email in the caller's transaction (the transactional outbox,
    ADR-011): it is sent by the worker only if the business change commits."""

    async def add(
        self,
        *,
        user_id: UUID | None,
        recipient_email: str,
        template: str,
        payload: dict[str, Any],
    ) -> EmailOutboxMessage: ...
