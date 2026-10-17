"""The order status projection (SRS 20.2). Pure; the only writer of `orders.status`."""

from dataclasses import dataclass

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod

TERMINAL_LINE_STATES = frozenset(
    {
        OrderItemStatus.DELIVERED,
        OrderItemStatus.PICKED_UP,
        OrderItemStatus.REFUNDED,
        OrderItemStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class LineState:
    status: OrderItemStatus


@dataclass(frozen=True)
class OrderStatusInputs:
    """`payment_reached_paid`: a payment is paid, partially_refunded or refunded. The two
    refund inputs stay False until VS-030 computes them."""

    payment_method: PaymentMethod
    cancelled_at_set: bool
    payment_reached_paid: bool
    lines: tuple[LineState, ...]
    refunds_cover_paid: bool = False
    refund_present: bool = False


def derive_order_status(i: OrderStatusInputs) -> OrderStatus:
    """SRS 20.2 exactly as written (SRS.md:1172-1186); a reorder is VS-030's decision."""
    states = [line.status for line in i.lines]
    all_cancelled = bool(states) and all(s is OrderItemStatus.CANCELLED for s in states)
    if not i.payment_reached_paid:
        if i.payment_method is PaymentMethod.ONLINE:
            return OrderStatus.CANCELLED if i.cancelled_at_set else OrderStatus.PENDING_PAYMENT
        return OrderStatus.CANCELLED if all_cancelled else OrderStatus.IN_PROGRESS
    if all_cancelled:
        return OrderStatus.CANCELLED
    if i.refunds_cover_paid:
        return OrderStatus.REFUNDED
    if states and all(s is OrderItemStatus.REFUNDED for s in states):
        return OrderStatus.REFUNDED
    if i.refund_present:
        return OrderStatus.PARTIALLY_REFUNDED
    if states and all(s in TERMINAL_LINE_STATES for s in states):
        return OrderStatus.COMPLETED
    return OrderStatus.IN_PROGRESS
