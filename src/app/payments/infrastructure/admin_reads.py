"""The admin payment reads (VS-024 plan 2.2): a keyset page ordered by `(initiated_at, id)`
and one payment's detail. Read-only and unlocked; never provider metadata (so no redirect
URL), webhook payloads or the customer's email."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.infrastructure.models import PaymentModel, WebhookEventModel
from app.payments.infrastructure.webhook_events import MANUAL_CONFIRMATION_REQUIRED

_P, _E = PaymentModel, WebhookEventModel


@dataclass(frozen=True)
class PaymentFilters:
    statuses: tuple[PaymentStatus, ...] = ()
    provider: PaymentProvider | None = None
    order_id: UUID | None = None
    late_captured: bool | None = None
    initiated_after: datetime | None = None
    initiated_before: datetime | None = None
    awaiting_confirmation: bool = False  # live `manual` attempts (ADR-049 d8)


@dataclass(frozen=True)
class AdminPaymentRow:
    id: UUID
    order_id: UUID
    provider: PaymentProvider
    status: PaymentStatus
    amount_cents: int
    currency: str
    captured_amount_cents: int | None
    captured_currency: str | None
    provider_payment_id: str | None
    initiated_at: datetime
    verified_at: datetime | None
    failed_at: datetime | None
    expired_at: datetime | None
    late_captured_at: datetime | None
    unprocessed_event_count: int
    needs_manual_confirmation: bool


@dataclass(frozen=True)
class EventRow:
    id: UUID
    event_type: str | None
    signature_valid: bool | None
    received_at: datetime
    processed_at: datetime | None
    processing_error: str | None


_unprocessed = (
    select(func.count())
    .select_from(_E)
    .where(_E.payment_id == _P.id, _E.processed_at.is_(None))
    .correlate(_P)
    .scalar_subquery()
)
# A `manual` attempt is pending until its confirm: `ix_payments_awaiting_manual`.
_MANUAL_PENDING = and_(_P.provider == PaymentProvider.MANUAL, _P.status == PaymentStatus.PENDING)
_awaiting_manual = or_(
    _MANUAL_PENDING,
    exists(
        select(_E.id).where(
            _E.payment_id == _P.id,
            _E.processed_at.is_(None),
            _E.processing_error == MANUAL_CONFIRMATION_REQUIRED,
        )
    ).correlate(_P),
)
_COLUMNS = (
    _P.id,
    _P.order_id,
    _P.provider,
    _P.status,
    _P.amount_cents,
    _P.currency,
    _P.captured_amount_cents,
    _P.captured_currency,
    _P.provider_payment_id,
    _P.initiated_at,
    _P.verified_at,
    _P.failed_at,
    _P.expired_at,
    _P.late_captured_at,
    _unprocessed.label("unprocessed_event_count"),
    _awaiting_manual.label("needs_manual_confirmation"),
)


def payment_page_query(
    filters: PaymentFilters, *, after: tuple[datetime, UUID] | None, limit: int
) -> Select[Any]:
    """Oldest first; `late_captured=true` is served by `ix_payments_late_captured`."""
    conditions: list[Any] = []
    if filters.statuses:
        conditions.append(_P.status.in_(filters.statuses))
    if filters.provider is not None:
        conditions.append(_P.provider == filters.provider)
    if filters.order_id is not None:
        conditions.append(_P.order_id == filters.order_id)
    if filters.late_captured is True:
        conditions.append(_P.late_captured_at.is_not(None))
    if filters.late_captured is False:
        conditions.append(_P.late_captured_at.is_(None))
    if filters.initiated_after is not None:
        conditions.append(_P.initiated_at >= filters.initiated_after)
    if filters.initiated_before is not None:
        conditions.append(_P.initiated_at < filters.initiated_before)
    if filters.awaiting_confirmation:
        conditions.append(_MANUAL_PENDING)
    if after is not None:
        conditions.append(tuple_(_P.initiated_at, _P.id) > after)
    return (
        select(*_COLUMNS)
        .where(and_(True, *conditions))
        .order_by(_P.initiated_at, _P.id)
        .limit(limit)
    )


def _row(row: Any) -> AdminPaymentRow:
    return AdminPaymentRow(**{key: getattr(row, key) for key in AdminPaymentRow.__annotations__})


async def payment_page(
    session: AsyncSession,
    filters: PaymentFilters,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[AdminPaymentRow]:
    rows = await session.execute(payment_page_query(filters, after=after, limit=limit))
    return [_row(row) for row in rows]


async def payment_row(session: AsyncSession, payment_id: UUID) -> AdminPaymentRow | None:
    row = (await session.execute(select(*_COLUMNS).where(_P.id == payment_id))).first()
    return _row(row) if row is not None else None


async def payment_events(session: AsyncSession, payment_id: UUID) -> list[EventRow]:
    """The payment's webhook events, oldest first, without their payloads."""
    rows = await session.execute(
        select(
            _E.id,
            _E.event_type,
            _E.signature_valid,
            _E.received_at,
            _E.processed_at,
            _E.processing_error,
        )
        .where(_E.payment_id == payment_id)
        .order_by(_E.received_at, _E.id)
    )
    return [EventRow(**row._mapping) for row in rows]
