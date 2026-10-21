"""`status_inputs_for` and the delivery's effect on the projection (VS-023b)."""

from datetime import UTC, datetime
from uuid import uuid4

from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import LineState, derive_order_status
from app.ordering.domain.orders import Order
from app.ordering.public import LockedOrder, status_inputs_for


def _order(status: OrderStatus) -> Order:
    return Order(
        id=uuid4(),
        order_number="BK-1",
        user_id=uuid4(),
        customer_email_snapshot="a@example.com",
        source=OrderSource.CART,
        status=status,
        fulfillment_method=None,
        payment_method=PaymentMethod.ONLINE,
        subtotal_cents=100,
        tax_cents=0,
        total_cents=100,
        currency="USD",
        placed_at=datetime(2026, 10, 21, tzinfo=UTC),
        cancelled_at=None,
    )


def _status(order_status: OrderStatus, *lines: S) -> OrderStatus:
    states = tuple(LineState(line) for line in lines)
    return derive_order_status(status_inputs_for(LockedOrder(_order(order_status), ()), states))


def test_the_only_stl_line_delivered_completes_the_order() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED) is OrderStatus.COMPLETED


def test_a_pending_physical_line_keeps_the_order_in_progress() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED, S.PENDING) is OrderStatus.IN_PROGRESS


def test_a_partially_refunded_order_stays_partially_refunded_after_delivery() -> None:
    """The stop-gap: VS-030 must compute `refund_present` from real refunds instead."""
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.DELIVERED) is OrderStatus.PARTIALLY_REFUNDED
