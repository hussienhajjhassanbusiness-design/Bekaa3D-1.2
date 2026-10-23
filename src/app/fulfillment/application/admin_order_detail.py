"""`AdminOrderDetail` (VS-029; SRS 8.7, ADR-025): the order, its lines with the actions the
transition endpoint would accept now, the full history and every payment. No lock."""

from dataclasses import dataclass
from uuid import UUID

from app.fulfillment.application.ports import AdminOrderReads, OrderPayments
from app.ordering.public import (
    AdminHistoryEntry,
    AdminOrder,
    AdminOrderLine,
    LineContext,
    OrderItemStatus,
    available_targets,
    payment_due,
)
from app.payments.public import OrderPaymentRow


@dataclass(frozen=True)
class LineWithActions:
    line: AdminOrderLine
    available: tuple[OrderItemStatus, ...]


@dataclass(frozen=True)
class AdminOrderView:
    order: AdminOrder
    lines: list[LineWithActions]
    history: list[AdminHistoryEntry]
    payments: list[OrderPaymentRow]
    payment_due: bool
    payment_reached_paid: bool


async def admin_order_detail(
    reads: AdminOrderReads, payments: OrderPayments, order_id: UUID
) -> AdminOrderView | None:
    order = await reads.get(order_id)
    if order is None:
        return None
    paid = await payments.reached_paid(order_id)
    lines = [
        LineWithActions(
            line,
            available_targets(
                LineContext(
                    line.product_type, order.fulfillment_method, order.payment_method, paid
                ),
                line.fulfillment_status,
            ),
        )
        for line in await reads.lines(order_id)
    ]
    return AdminOrderView(
        order=order,
        lines=lines,
        history=await reads.history(order_id),
        payments=await payments.rows(order_id),
        payment_due=payment_due(
            status=order.status, payment_method=order.payment_method, reached_paid=paid
        ),
        payment_reached_paid=paid,
    )
