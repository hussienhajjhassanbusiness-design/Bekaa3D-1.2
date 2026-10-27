"""Ordering's reporting reads (VS-043). Unlocked, read-only; Ordering's own tables only."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus
from app.ordering.infrastructure.models import OrderItemModel, OrderModel

_CHUNK = 5_000
_I, _O = OrderItemModel, OrderModel


def _chunks(ids: Sequence[UUID]) -> Iterator[list[UUID]]:
    for start in range(0, len(ids), _CHUNK):
        yield list(ids[start : start + _CHUNK])


@dataclass(frozen=True)
class ReportLineRow:
    id: UUID
    order_id: UUID
    user_id: UUID
    product_id: UUID
    product_type: str
    name_snapshot: str
    status: str
    quantity: int
    line_total_cents: int


@dataclass(frozen=True)
class ReportOrderRow:
    order_number: str
    payment_method: str
    user_id: UUID


async def report_lines(session: AsyncSession, order_ids: Sequence[UUID]) -> list[ReportLineRow]:
    """Every line of these orders, in any state; the report decides which are paid."""
    out: list[ReportLineRow] = []
    for chunk in _chunks(order_ids):
        query = select(
            _I.id,
            _I.order_id,
            _I.user_id,
            _I.product_id,
            _I.product_type,
            _I.product_name_snapshot,
            _I.fulfillment_status,
            _I.quantity,
            _I.line_total_cents,
        ).where(_I.order_id.in_(chunk))
        for row in (await session.execute(query)).tuples():
            line_id, order_id, user_id, product_id, kind, name, status, quantity, total = row
            out.append(
                ReportLineRow(
                    line_id,
                    order_id,
                    user_id,
                    product_id,
                    str(kind),
                    name,
                    str(status),
                    quantity,
                    total,
                )
            )
    return out


async def report_orders(
    session: AsyncSession, order_ids: Sequence[UUID]
) -> dict[UUID, ReportOrderRow]:
    out: dict[UUID, ReportOrderRow] = {}
    for chunk in _chunks(order_ids):
        query = select(_O.id, _O.order_number, _O.payment_method, _O.user_id).where(
            _O.id.in_(chunk)
        )
        for order_id, number, method, user_id in (await session.execute(query)).tuples():
            out[order_id] = ReportOrderRow(number, str(method), user_id)
    return out


async def order_ids_for_user(session: AsyncSession, user_id: UUID) -> list[UUID]:
    query = select(_O.id).where(_O.user_id == user_id)
    return list((await session.execute(query)).scalars())


async def stl_awaiting_delivery_counts(session: AsyncSession) -> dict[UUID, int]:
    """STL lines awaiting delivery now, by product (`ix_order_items_stl_awaiting`)."""
    query = (
        select(_I.product_id, func.count())
        .where(
            _I.product_type == ProductType.STL,
            _I.fulfillment_status == OrderItemStatus.AWAITING_DELIVERY,
        )
        .group_by(_I.product_id)
    )
    return {product_id: int(n) for product_id, n in (await session.execute(query)).tuples()}
