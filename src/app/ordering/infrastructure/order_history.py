"""`SqlOrderHistory` (VS-025): the customer's reads. Every query names the caller in its
predicate, and the column lists never include `admin_note` (plan Q7, Q8)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import OrderFilters
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry
from app.ordering.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderStatusHistoryModel,
)

_O, _I, _H = OrderModel, OrderItemModel, OrderStatusHistoryModel
_ORDER_COLUMNS = (
    _O.id,
    _O.order_number,
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
    _O.estimated_dispatch_at,
    _O.placed_at,
    _O.completed_at,
    _O.cancelled_at,
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
    _I.cancelled_at,
    _I.offer_id,
)


def _order(row: Any) -> CustomerOrder:
    return CustomerOrder(**{c.key: getattr(row, c.key) for c in _ORDER_COLUMNS})


class SqlOrderHistory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(
        self,
        user_id: UUID,
        filters: OrderFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[CustomerOrder]:
        query = select(*_ORDER_COLUMNS).where(_O.user_id == user_id)
        if filters.status is not None:
            query = query.where(_O.status == filters.status)
        if filters.placed_after is not None:
            query = query.where(_O.placed_at >= filters.placed_after)
        if filters.placed_before is not None:
            query = query.where(_O.placed_at < filters.placed_before)
        if after is not None:
            query = query.where(tuple_(_O.placed_at, _O.id) < tuple_(*after))
        query = query.order_by(_O.placed_at.desc(), _O.id.desc()).limit(limit)
        return [_order(row) for row in (await self._session.execute(query)).all()]

    async def get(self, user_id: UUID, order_id: UUID) -> CustomerOrder | None:
        row = (
            await self._session.execute(
                select(*_ORDER_COLUMNS).where(_O.id == order_id, _O.user_id == user_id)
            )
        ).first()
        return _order(row) if row is not None else None

    async def lines(self, user_id: UUID, order_id: UUID) -> list[CustomerOrderLine]:
        result = await self._session.execute(
            select(*_LINE_COLUMNS)
            .join(_O, _O.id == _I.order_id)
            .where(_I.order_id == order_id, _O.user_id == user_id)
            .order_by(_I.created_at, _I.id)
        )
        return [
            CustomerOrderLine(**{c.key: getattr(row, c.key) for c in _LINE_COLUMNS})
            for row in result.all()
        ]

    async def history(self, user_id: UUID, order_id: UUID) -> list[HistoryEntry]:
        result = await self._session.execute(
            select(_H.order_item_id, _H.from_status, _H.to_status, _H.created_at)
            .join(_O, _O.id == _H.order_id)
            .where(_H.order_id == order_id, _O.user_id == user_id)
            .order_by(_H.created_at, _H.id)
        )
        return [HistoryEntry(*row) for row in result.all()]
