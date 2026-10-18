"""`SqlWebhookEventStore` (database-design 9.2; VS-023 plan 4.6). It never commits and
takes no row lock: deduplication is the unique key, processing is idempotent."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.application.ports import NewWebhookEvent, WebhookEvent
from app.payments.infrastructure.models import WebhookEventModel

_E = WebhookEventModel


class SqlWebhookEventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_if_new(self, event: NewWebhookEvent) -> UUID | None:
        """None when `(provider, provider_event_id)` was already stored (BR-056)."""
        new_id: UUID | None = await self._session.scalar(
            insert(_E)
            .values(**vars(event))
            .on_conflict_do_nothing(constraint="uq_webhook_events_provider_event")
            .returning(_E.id)
        )
        return new_id

    async def get(self, event_id: UUID) -> WebhookEvent | None:
        row = (
            await self._session.execute(
                select(_E.id, _E.provider, _E.payment_id, _E.processed_at).where(_E.id == event_id)
            )
        ).first()
        if row is None:
            return None
        return WebhookEvent(
            id=row.id,
            provider=row.provider,
            payment_id=row.payment_id,
            processed_at=row.processed_at,
        )

    async def unprocessed_ids(self, limit: int) -> list[UUID]:
        """Oldest first, served by `ix_webhook_events_unprocessed`."""
        result = await self._session.scalars(
            select(_E.id)
            .where(_E.processed_at.is_(None))
            .order_by(_E.received_at, _E.id)
            .limit(limit)
        )
        return list(result.all())

    async def mark_processed(self, event_id: UUID, *, at: datetime) -> None:
        """Last statement of Tx B (plan 8.1); a second verifier's update is a no-op."""
        await self._session.execute(
            update(_E)
            .where(_E.id == event_id, _E.processed_at.is_(None))
            .values(processed_at=at, processing_error=None)
        )

    async def record_error(self, event_id: UUID, error: str) -> None:
        """The event stays unprocessed: the next `verify_payments` run retries it."""
        await self._session.execute(
            update(_E)
            .where(_E.id == event_id, _E.processed_at.is_(None))
            .values(processing_error=error)
        )
