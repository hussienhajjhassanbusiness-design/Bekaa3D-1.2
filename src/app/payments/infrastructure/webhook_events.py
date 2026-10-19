"""`SqlWebhookEventStore` (database-design 9.2; VS-023 plan 4.6). It never commits and
takes no row lock: deduplication is the unique key, processing is idempotent."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.application.ports import NewWebhookEvent, WebhookEvent
from app.payments.infrastructure.models import WebhookEventModel

_E = WebhookEventModel
# `processing_error` values verification leaves on an unprocessed event (VS-024 3.2a, 3.3).
MANUAL_CONFIRMATION_REQUIRED = "manual_confirmation_required"
PROVIDER_UNKNOWN_REFERENCE = "provider_unknown_reference"
DISMISSED_BY_ADMIN = "dismissed_by_admin"


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
        """Oldest first, served by `ix_webhook_events_unprocessed`. An event awaiting manual
        confirmation is never retried here, so it cannot block the head of the queue."""
        result = await self._session.scalars(
            select(_E.id)
            .where(
                _E.processed_at.is_(None),
                _E.processing_error.is_distinct_from(MANUAL_CONFIRMATION_REQUIRED),
            )
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

    async def count_unprocessed_for_payment(self, payment_id: UUID) -> int:
        """Served by `ix_webhook_events_payment_unprocessed`."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(_E)
            .where(_E.payment_id == payment_id, _E.processed_at.is_(None))
        )
        return int(count or 0)

    async def mark_processed_for_payment(self, payment_id: UUID, *, at: datetime) -> int:
        """Every unprocessed event of the payment; the number marked."""
        result = await self._session.execute(
            update(_E)
            .where(_E.payment_id == payment_id, _E.processed_at.is_(None))
            .values(processed_at=at, processing_error=None)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def count_unprocessed_for_payments(self, payment_ids: Sequence[UUID]) -> int:
        """Across the order's attempts; unlocked (`ix_webhook_events_payment_unprocessed`)."""
        if not payment_ids:
            return 0
        count = await self._session.scalar(
            select(func.count())
            .select_from(_E)
            .where(_E.payment_id.in_(payment_ids), _E.processed_at.is_(None))
        )
        return int(count or 0)

    async def dismiss_for_payments(
        self, payment_ids: Sequence[UUID], *, at: datetime
    ) -> list[UUID]:
        """The manual release's reviewed events (plan 2.5): processed, `dismissed_by_admin`."""
        result = await self._session.scalars(
            update(_E)
            .where(_E.payment_id.in_(payment_ids), _E.processed_at.is_(None))
            .values(processed_at=at, processing_error=DISMISSED_BY_ADMIN)
            .returning(_E.id)
        )
        return sorted(result.all(), key=str)
