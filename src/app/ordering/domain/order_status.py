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
class RefundFacts:
    """Read under the orders lock (ADR-042); `late_capture` and voided refunds never count.
    covers_paid: pending + settled + chargeback applied >= paid. present: any of those.
    owed: a failed refund not yet reissued."""

    covers_paid: bool = False
    present: bool = False
    owed: bool = False


NO_REFUNDS = RefundFacts()


@dataclass(frozen=True)
class OrderStatusInputs:
    """`payment_reached_paid`: a payment is paid, partially_refunded or refunded. `refunds`
    is read by the caller under the orders lock (ADR-042)."""

    payment_method: PaymentMethod
    cancelled_at_set: bool
    payment_reached_paid: bool
    lines: tuple[LineState, ...]
    refunds: RefundFacts = NO_REFUNDS


def derive_order_status(i: OrderStatusInputs) -> OrderStatus:
    """SRS 20.2 as amended by ADR-042: once paid, an owed refund is checked first, and the
    "all lines refunded" rule is gone (it only fired when refunds already covered)."""
    states = [line.status for line in i.lines]
    all_cancelled = bool(states) and all(s is OrderItemStatus.CANCELLED for s in states)
    if not i.payment_reached_paid:
        if i.payment_method is PaymentMethod.ONLINE:
            return OrderStatus.CANCELLED if i.cancelled_at_set else OrderStatus.PENDING_PAYMENT
        return OrderStatus.CANCELLED if all_cancelled else OrderStatus.IN_PROGRESS
    if i.refunds.owed:
        return OrderStatus.PARTIALLY_REFUNDED
    if all_cancelled:
        return OrderStatus.CANCELLED
    if i.refunds.covers_paid:
        return OrderStatus.REFUNDED
    if i.refunds.present:
        return OrderStatus.PARTIALLY_REFUNDED
    if states and all(s in TERMINAL_LINE_STATES for s in states):
        return OrderStatus.COMPLETED
    return OrderStatus.IN_PROGRESS
