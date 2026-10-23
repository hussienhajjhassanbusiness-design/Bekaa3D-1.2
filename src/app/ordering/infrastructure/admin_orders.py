"""`SqlAdminOrders` (VS-029): the administrator's order reads. No lock; the queue never
lists an unpaid online order (BR-148), and its pages match `ix_orders_admin_queue`."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, not_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.domain.admin_orders import (
    AdminHistoryEntry,
    AdminOrder,
    AdminOrderFilters,
    AdminOrderLine,
)
from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.infrastructure.models import (
    ADMIN_QUEUE_PREDICATE,
    OrderItemModel,
    OrderModel,
    OrderStatusHistoryModel,
)

_O, _I, _H = OrderModel, OrderItemModel, OrderStatusHistoryModel
_ORDER_COLUMNS = (
    _O.id,
    _O.order_number,
    _O.user_id,
    _O.customer_email_snapshot,
    _O.source,
    _O.status,
    _O.fulfillment_method,
    _O.payment_method,
    _O.subtotal_cents,
    _O.tax_cents,
    _O.total_cents,
    _O.currency,
    _O.recipient_name,
    _O.contact_phone_snapshot,
    _O.governorate,
    _O.city,
    _O.area,
    _O.street,
    _O.landmark_notes,
    _O.customer_note,
    _O.admin_note,
    _O.estimated_dispatch_at,
    _O.placed_at,
    _O.completed_at,
    _O.cancelled_at,
    (
        select(func.coalesce(func.sum(_I.line_total_cents), 0))
        .where(_I.order_id == _O.id, _I.fulfillment_status != OrderItemStatus.CANCELLED)
        .scalar_subquery()
        .label("live_total_cents")
    ),
)
_LINE_COLUMNS = (
    _I.id,
    _I.product_id,
    _I.product_type,
    _I.product_name_snapshot,
    _I.image_snapshot,
    _I.unit_price_cents,
    _I.quantity,
    _I.line_total_cents,
    _I.currency,
    _I.fulfillment_status,
    _I.fulfilled_at,
    _I.delivered_by,
    _I.cancelled_at,
    _I.cancel_reason,
    _I.offer_id,
    _I.lead_time_days_snapshot,
    _I.batch_size_snapshot,
    _I.receipt_confirmed_at,
    _I.problem_reported_at,
)
_CASH_DUE = and_(_O.payment_method == PaymentMethod.CASH, _O.status == OrderStatus.IN_PROGRESS)


def _order(row: Any) -> AdminOrder:
    return AdminOrder(**{c.key: getattr(row, c.key) for c in _ORDER_COLUMNS})


def admin_queue_query(
    filters: AdminOrderFilters, *, after: tuple[datetime, UUID] | None, limit: int
) -> Select[Any]:
    """The queue selection, also EXPLAINed by its test. Newest first by `(placed_at, id)`."""
    query = select(*_ORDER_COLUMNS).where(text(ADMIN_QUEUE_PREDICATE))
    f = filters
    if f.payment_due is True:
        query = query.where(_CASH_DUE)
    elif f.payment_due is False:
        query = query.where(not_(_CASH_DUE))
    for column, value in (
        (_O.status, f.status),
        (_O.fulfillment_method, f.fulfillment_method),
        (_O.payment_method, f.payment_method),
        (_O.user_id, f.customer_id),
        (_O.order_number, f.order_number),
    ):
        if value is not None:
            query = query.where(column == value)
    if f.placed_after is not None:
        query = query.where(_O.placed_at >= f.placed_after)
    if f.placed_before is not None:
        query = query.where(_O.placed_at < f.placed_before)
    if after is not None:
        query = query.where(tuple_(_O.placed_at, _O.id) < tuple_(*after))
    return query.order_by(_O.placed_at.desc(), _O.id.desc()).limit(limit)


class SqlAdminOrders:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(
        self, filters: AdminOrderFilters, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[AdminOrder]:
        query = admin_queue_query(filters, after=after, limit=limit)
        return [_order(row) for row in (await self._session.execute(query)).all()]

    async def get(self, order_id: UUID) -> AdminOrder | None:
        """Any order, the unpaid online ones included: a detail is not the queue."""
        row = (
            await self._session.execute(select(*_ORDER_COLUMNS).where(_O.id == order_id))
        ).first()
        return _order(row) if row is not None else None

    async def lines(self, order_id: UUID) -> list[AdminOrderLine]:
        result = await self._session.execute(
            select(*_LINE_COLUMNS).where(_I.order_id == order_id).order_by(_I.created_at, _I.id)
        )
        return [
            AdminOrderLine(**{c.key: getattr(row, c.key) for c in _LINE_COLUMNS})
            for row in result.all()
        ]

    async def history(self, order_id: UUID) -> list[AdminHistoryEntry]:
        result = await self._session.execute(
            select(
                _H.order_item_id,
                _H.from_status,
                _H.to_status,
                _H.actor_user_id,
                _H.reason,
                _H.created_at,
            )
            .where(_H.order_id == order_id)
            .order_by(_H.created_at, _H.id)
        )
        return [AdminHistoryEntry(*row) for row in result.all()]

    async def set_admin_note(self, order_id: UUID, note: str | None, *, at: datetime) -> bool:
        """The internal note only; never a line, payment or status (F-062)."""
        result = await self._session.execute(
            update(_O).where(_O.id == order_id).values(admin_note=note, updated_at=at)
        )
        return int(getattr(result, "rowcount", 0)) == 1
