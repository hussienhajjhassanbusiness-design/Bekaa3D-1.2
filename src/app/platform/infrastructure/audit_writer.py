"""The SQL adapters behind Platform's published write ports.

`SqlAuditWriter` implements `app.platform.application.ports.AuditWriter` and
`SqlOutboxWriter` implements `OutboxWriter`. Other contexts never import this
module: they get these classes from `app.platform.public` and type against the
ports, so cross-context access goes through a service interface rather than
another context's infrastructure (CLAUDE.md, architecture rules; BUG-41).

Both take the caller's `AsyncSession` rather than opening their own, and
**never commit**. That is the whole point: BR-132 requires a business mutation
and its audit record to land together, which is only achievable if both run in
one transaction owned by the caller. A writer that committed on its own could
leave an audit row describing a change that was still able to fail.

Introduced by VS-010 as `AuditWriter`; moved here and renamed in VS-012c.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.entities import EmailOutboxMessage
from app.platform.infrastructure.repositories import AuditLogRepository, EmailOutboxRepository


class SqlAuditWriter:
    """The sanctioned way for another context to append an audit record."""

    def __init__(self, session: AsyncSession) -> None:
        self._audit = AuditLogRepository(session)

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
    ) -> None:
        """Append one audit row inside the caller's transaction.

        Returns nothing: callers need the record written, not the row back, and
        handing out the persisted entity would invite another context to start
        depending on Platform's `AuditLogEntry` shape.
        """
        await self._audit.add(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id,
            ip_hash=ip_hash,
        )

    async def recorded(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        matching: dict[str, str],
        since: datetime | None,
    ) -> bool:
        """Whether such a row exists (after `since`, when given): de-duplication by audit row."""
        return await self._audit.exists(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            matching=matching,
            since=since,
        )


class SqlOutboxWriter:
    """Queue a transactional email in the caller's transaction (ADR-011)."""

    def __init__(self, session: AsyncSession) -> None:
        self._outbox = EmailOutboxRepository(session)

    async def add(
        self,
        *,
        user_id: UUID | None,
        recipient_email: str,
        template: str,
        payload: dict[str, Any],
    ) -> EmailOutboxMessage:
        return await self._outbox.add(
            user_id=user_id, recipient_email=recipient_email, template=template, payload=payload
        )
