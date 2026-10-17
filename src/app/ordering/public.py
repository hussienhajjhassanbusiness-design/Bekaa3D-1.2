"""Ordering's published surface for other contexts (frozen at VS-023 Checkpoint 2).

Every write here follows the ADR-024 lock order: the `orders` row first, then its lines
by id; a caller that also locks a payment does so only after `lock_order_for_change`."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import (
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.order_status import LineState, OrderStatusInputs, derive_order_status
from app.ordering.domain.orders import Order, OrderLine, StatusChange
from app.ordering.infrastructure.orders import SqlOrderStore

__all__ = [
    "CancelReason",
    "FulfillmentMethod",
    "LineState",
    "LockedOrder",
    "OrderItemStatus",
    "OrderSource",
    "OrderStatus",
    "OrderStatusInputs",
    "PaymentMethod",
    "derive_order_status",
    "lock_order_for_change",
    "mark_order_paid",
    "recompute_order_status",
    "stl_owned",
]


@dataclass(frozen=True)
class LockedOrder:
    order: Order
    lines: tuple[OrderLine, ...]


async def lock_order_for_change(session: AsyncSession, order_id: UUID) -> LockedOrder | None:
    """ADR-024 d9 steps 1-2: `orders` FOR UPDATE, then every line FOR UPDATE by id."""
    store = SqlOrderStore(session)
    order = await store.lock_order(order_id)
    if order is None:
        return None
    return LockedOrder(order=order, lines=tuple(await store.lock_lines(order_id)))


async def recompute_order_status(
    session: AsyncSession, locked: LockedOrder, inputs: OrderStatusInputs
) -> OrderStatus:
    """The only writer of `orders.status`; a history row only when it changes."""
    status = derive_order_status(inputs)
    if status is not locked.order.status:
        at = datetime.now(UTC)
        store = SqlOrderStore(session)
        await store.set_order_status(locked.order.id, status, at=at)
        await store.add_history(
            [StatusChange(locked.order.id, locked.order.status.value, status.value)]
        )
    return status


async def mark_order_paid(session: AsyncSession, locked: LockedOrder, *, at: datetime) -> None:
    """Payment verified: STL lines `pending -> awaiting_delivery` (ADR-019 d2), physical
    lines stay `pending`; history rows, then the recomputed status. Caller holds the locks."""
    store = SqlOrderStore(session)
    stl = [
        line
        for line in locked.lines
        if line.product_type is ProductType.STL
        and line.fulfillment_status is OrderItemStatus.PENDING
    ]
    await store.set_line_status([line.id for line in stl], OrderItemStatus.AWAITING_DELIVERY, at=at)
    await store.add_history(
        [
            StatusChange(
                locked.order.id,
                OrderItemStatus.PENDING.value,
                OrderItemStatus.AWAITING_DELIVERY.value,
                order_item_id=line.id,
            )
            for line in stl
        ]
    )
    moved = {line.id for line in stl}
    states = tuple(
        LineState(
            OrderItemStatus.AWAITING_DELIVERY if line.id in moved else line.fulfillment_status
        )
        for line in locked.lines
    )
    await recompute_order_status(
        session,
        locked,
        OrderStatusInputs(
            payment_method=locked.order.payment_method,
            cancelled_at_set=locked.order.cancelled_at is not None,
            payment_reached_paid=True,
            lines=states,
        ),
    )


async def stl_owned(session: AsyncSession, *, user_id: UUID, product_id: UUID) -> bool:
    """A paid, unrefunded STL line (`awaiting_delivery` or `delivered`), ADR-019 d5."""
    return bool(await SqlOrderStore(session).owned_stl_product_ids(user_id, [product_id]))
