"""`status_inputs_for` and the effect of deliveries and handovers on the projection."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import (
    NO_REFUNDS,
    LineState,
    RefundFacts,
    derive_order_status,
)
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
    refunds: RefundFacts = NO_REFUNDS,
) -> OrderStatus:
    states = tuple(LineState(line) for line in lines)
    locked = LockedOrder(_order(order_status, payment), ())
    inputs = status_inputs_for(locked, states, reached_paid=paid, refunds=refunds)
    return derive_order_status(inputs)


def test_the_only_stl_line_delivered_completes_the_order() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED) is OrderStatus.COMPLETED


def test_a_pending_physical_line_keeps_the_order_in_progress() -> None:
    assert _status(OrderStatus.IN_PROGRESS, S.DELIVERED, S.PENDING) is OrderStatus.IN_PROGRESS


def test_a_partially_refunded_order_stays_partially_refunded_after_delivery() -> None:
    """From the refund facts, never from the order's previous status (ADR-042)."""
    present = RefundFacts(present=True)
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.DELIVERED, refunds=present) is (
        OrderStatus.PARTIALLY_REFUNDED
    )
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.DELIVERED) is OrderStatus.COMPLETED


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


def test_refund_facts_never_apply_to_an_unpaid_order() -> None:
    every = RefundFacts(covers_paid=True, present=True, owed=True)
    assert _status(OrderStatus.PARTIALLY_REFUNDED, S.SHIPPED, paid=False, refunds=every) is (
        OrderStatus.PENDING_PAYMENT
    )


@pytest.mark.xfail(strict=True, reason="VS-030 replaces the refund_present stop-gap (ADR-039 d7)")
def test_a_refunded_order_stays_refunded_after_a_physical_transition() -> None:
    assert _status(OrderStatus.REFUNDED, S.IN_PRODUCTION) is OrderStatus.REFUNDED
