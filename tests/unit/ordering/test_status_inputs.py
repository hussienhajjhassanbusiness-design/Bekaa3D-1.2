"""`status_inputs_for` and the effect of deliveries and handovers on the projection."""

from datetime import UTC, datetime
from uuid import uuid4

from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import LineState, derive_order_status
from app.ordering.domain.orders import Order
from app.ordering.public import LockedOrder, status_inputs_for


def _order(status: OrderStatus, payment: PaymentMethod = PaymentMethod.ONLINE) -> Order:
    return Order(
        id=uuid4(),
        order_number="BK-1",
        user_id=uuid4(),
        customer_email_snapshot="a@example.com",
        source=OrderSource.CART,
        status=status,
        fulfillment_method=None,
        payment_method=payment,
        subtotal_cents=100,
        tax_cents=0,
        total_cents=100,
        currency="USD",
        placed_at=datetime(2026, 10, 21, tzinfo=UTC),
        cancelled_at=None,
    )


def _status(
    order_status: OrderStatus,
    *lines: S,
    paid: bool = True,
    payment: PaymentMethod = PaymentMethod.ONLINE,
) -> OrderStatus:
    states = tuple(LineState(line) for line in lines)
    locked = LockedOrder(_order(order_status, payment), ())
    return derive_order_status(status_inputs_for(locked, states, reached_paid=paid))


def test_the_only_stl_line_delivered_completes_the_order() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED) is OrderStatus.COMPLETED


def test_a_pending_physical_line_keeps_the_order_in_progress() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED, S.PENDING) is OrderStatus.IN_PROGRESS


def test_a_partially_refunded_order_stays_partially_refunded_after_delivery() -> None:
    """The stop-gap: VS-030 must compute `refund_present` from real refunds instead."""
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.DELIVERED) is OrderStatus.PARTIALLY_REFUNDED


def test_an_unpaid_cash_order_in_production_stays_in_progress() -> None:
    cash = PaymentMethod.CASH
    for line in (S.IN_PRODUCTION, S.SHIPPED, S.READY_FOR_PICKUP):
        assert _status(OrderStatus.IN_PROGRESS, line, paid=False, payment=cash) is (
            OrderStatus.IN_PROGRESS
        )


def test_a_handed_over_cash_order_completes_beside_a_cancelled_line() -> None:
    cash = PaymentMethod.CASH
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED, S.CANCELLED, payment=cash) is (
        OrderStatus.COMPLETED
    )


def test_the_refund_stop_gap_never_applies_to_an_unpaid_order() -> None:
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.SHIPPED, paid=False) is (
        OrderStatus.PENDING_PAYMENT
    )
