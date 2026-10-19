"""The customer's order history and order detail (VS-025; F-026, F-027)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.ordering.application.ports import (
    OrderFilters,
    OrderHistoryStore,
    OrderPaymentReader,
    OrderPaymentView,
    PaymentAttemptRef,
)
from app.ordering.domain.customer_view import (
    can_cancel,
    customer_history,
    customer_lines,
    payment_due,
)
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry

_UNPAID = OrderPaymentView(reached_paid=False, shown=None)


@dataclass(frozen=True)
class OrderSummaryView:
    order: CustomerOrder
    payment_due: bool


@dataclass(frozen=True)
class OrderDetailView:
    order: CustomerOrder
    lines: list[CustomerOrderLine]
    history: list[HistoryEntry]
    payment: PaymentAttemptRef | None
    payment_due: bool
    can_cancel: bool


async def list_orders(
    orders: OrderHistoryStore,
    payments: OrderPaymentReader,
    *,
    user_id: UUID,
    filters: OrderFilters,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[OrderSummaryView]:
    """One page, then one batched payment read for it."""
    page = await orders.page(user_id, filters, after=after, limit=limit)
    views = await payments.views([order.id for order in page])
    return [_summary(order, views.get(order.id, _UNPAID)) for order in page]


def _summary(order: CustomerOrder, view: OrderPaymentView) -> OrderSummaryView:
    due = payment_due(
        status=order.status, payment_method=order.payment_method, reached_paid=view.reached_paid
    )
    return OrderSummaryView(order=order, payment_due=due)


async def get_order(
    orders: OrderHistoryStore, payments: OrderPaymentReader, *, user_id: UUID, order_id: UUID
) -> OrderDetailView | None:
    """None for an unknown order and for another customer's alike."""
    order = await orders.get(user_id, order_id)
    if order is None:
        return None
    lines: Sequence[CustomerOrderLine] = await orders.lines(user_id, order_id)
    view = (await payments.views([order_id])).get(order_id, _UNPAID)
    return OrderDetailView(
        order=order,
        lines=customer_lines(lines),
        history=customer_history(await orders.history(user_id, order_id)),
        payment=view.shown,
        payment_due=_summary(order, view).payment_due,
        can_cancel=can_cancel(
            status=order.status,
            payment_method=order.payment_method,
            reached_paid=view.reached_paid,
            lines=lines,
        ),
    )
