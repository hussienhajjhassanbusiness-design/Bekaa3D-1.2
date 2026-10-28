"""VS-044's order read: the VS-025 customer columns and masks, a page of orders at a time,
with their lines and history batched. Never `admin_note`, the phone hash or an actor."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.customer_view import customer_history, customer_lines
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry
from app.ordering.infrastructure.models import OrderItemModel, OrderModel, OrderStatusHistoryModel
from app.ordering.infrastructure.order_history import _LINE_COLUMNS, _ORDER_COLUMNS, _order

_O, _I, _H = OrderModel, OrderItemModel, OrderStatusHistoryModel


@dataclass(frozen=True)
class ExportOrderRow:
    order: CustomerOrder
    delivery_email: str | None  # where the STL files were emailed; None without an STL line
    lines: list[CustomerOrderLine]
    history: list[HistoryEntry]


async def orders_for_export(
    session: AsyncSession, user_id: UUID, *, after: tuple[datetime, UUID] | None, limit: int
) -> list[ExportOrderRow]:
    """Oldest first, keyset on `(placed_at, id)`; every query names the caller."""
    query = select(*_ORDER_COLUMNS, _O.customer_email_snapshot).where(_O.user_id == user_id)
    if after is not None:
        query = query.where(tuple_(_O.placed_at, _O.id) > tuple_(*after))
    rows = (await session.execute(query.order_by(_O.placed_at, _O.id).limit(limit))).all()
    if not rows:
        return []
    order_ids = [row.id for row in rows]
    lines = await _lines(session, user_id, order_ids)
    history = await _history(session, user_id, order_ids)
    found = []
    for row in rows:
        own = lines[row.id]
        has_stl = any(line.product_type is ProductType.STL for line in own)
        found.append(
            ExportOrderRow(
                order=_order(row),
                delivery_email=row.customer_email_snapshot if has_stl else None,
                lines=customer_lines(own),
                history=customer_history(history[row.id]),
            )
        )
    return found


async def _lines(
    session: AsyncSession, user_id: UUID, order_ids: list[UUID]
) -> dict[UUID, list[CustomerOrderLine]]:
    result = await session.execute(
        select(_I.order_id, *_LINE_COLUMNS)
        .where(_I.order_id.in_(order_ids), _I.user_id == user_id)
        .order_by(_I.order_id, _I.created_at, _I.id)
    )
    grouped: dict[UUID, list[CustomerOrderLine]] = defaultdict(list)
    for row in result.all():
        line = CustomerOrderLine(**{c.key: getattr(row, c.key) for c in _LINE_COLUMNS})
        grouped[row.order_id].append(line)
    return grouped


async def _history(
    session: AsyncSession, user_id: UUID, order_ids: list[UUID]
) -> dict[UUID, list[HistoryEntry]]:
    result = await session.execute(
        select(_H.order_id, _H.order_item_id, _H.from_status, _H.to_status, _H.created_at)
        .join(_O, _O.id == _H.order_id)
        .where(_H.order_id.in_(order_ids), _O.user_id == user_id)
        .order_by(_H.order_id, _H.created_at, _H.id)
    )
    grouped: dict[UUID, list[HistoryEntry]] = defaultdict(list)
    for order_id, item_id, from_status, to_status, at in result.tuples():
        grouped[order_id].append(HistoryEntry(item_id, from_status, to_status, at))
    return grouped
