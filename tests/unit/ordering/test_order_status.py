"""derive_order_status: every SRS 20.2 branch, in the ADR-042 order (VS-030 plan 3.1, U1)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import (
    LineState,
    OrderStatusInputs,
    RefundFacts,
    derive_order_status,
)

S = OrderItemStatus
ONLINE, CASH = PaymentMethod.ONLINE, PaymentMethod.CASH


def inputs(method: PaymentMethod, *states: OrderItemStatus, **over: bool) -> OrderStatusInputs:
    return OrderStatusInputs(
        payment_method=method,
        cancelled_at_set=over.get("cancelled_at_set", False),
        payment_reached_paid=over.get("paid", False),
        lines=tuple(LineState(s) for s in states),
        refunds=RefundFacts(
            covers_paid=over.get("cover", False),
            present=over.get("refund", False),
            owed=over.get("owed", False),
        ),
    )


CASES = [
    ("online-unpaid", inputs(ONLINE, S.PENDING), OrderStatus.PENDING_PAYMENT),
    (
        "online-failed-attempt-stays-pending",
        inputs(ONLINE, S.PENDING, S.PENDING),
        OrderStatus.PENDING_PAYMENT,
    ),
    (
        "online-hold-released",
        inputs(ONLINE, S.CANCELLED, cancelled_at_set=True),
        OrderStatus.CANCELLED,
    ),
    ("cash-unpaid-live-line", inputs(CASH, S.PENDING, S.CANCELLED), OrderStatus.IN_PROGRESS),
    ("cash-unpaid-all-cancelled", inputs(CASH, S.CANCELLED, S.CANCELLED), OrderStatus.CANCELLED),
    ("paid-all-cancelled", inputs(ONLINE, S.CANCELLED, paid=True), OrderStatus.CANCELLED),
    (
        "paid-refunds-cover-paid-money",
        inputs(ONLINE, S.DELIVERED, S.PENDING, paid=True, cover=True, refund=True),
        OrderStatus.REFUNDED,
    ),
    # Realistic: a fully refunded line means refunds cover the paid money (ADR-042, I2).
    (
        "paid-all-lines-refunded",
        inputs(ONLINE, S.REFUNDED, paid=True, cover=True, refund=True),
        OrderStatus.REFUNDED,
    ),
    (
        "paid-refund-present",
        inputs(ONLINE, S.AWAITING_DELIVERY, paid=True, refund=True),
        OrderStatus.PARTIALLY_REFUNDED,
    ),
    ("paid-stl-delivered", inputs(ONLINE, S.DELIVERED, paid=True), OrderStatus.COMPLETED),
    ("paid-picked-up", inputs(CASH, S.PICKED_UP, paid=True), OrderStatus.COMPLETED),
    (
        "paid-terminal-mix",
        inputs(ONLINE, S.DELIVERED, S.REFUNDED, S.CANCELLED, paid=True),
        OrderStatus.COMPLETED,
    ),
    (
        "paid-awaiting-delivery",
        inputs(ONLINE, S.AWAITING_DELIVERY, paid=True),
        OrderStatus.IN_PROGRESS,
    ),
    ("paid-returned-is-not-terminal", inputs(CASH, S.RETURNED, paid=True), OrderStatus.IN_PROGRESS),
    # The PR #8 review cases (vertical-slice-plan.md:820), flipped by ADR-042: money still
    # owed never reads refunded (D-c, case A) or cancelled (D-a, case B).
    (
        "pr8-case-a-failed-full-refund-owed",
        inputs(ONLINE, S.REFUNDED, paid=True, owed=True),
        OrderStatus.PARTIALLY_REFUNDED,
    ),
    (
        "pr8-case-b-all-cancelled-refund-owed",
        inputs(ONLINE, S.CANCELLED, S.CANCELLED, paid=True, owed=True),
        OrderStatus.PARTIALLY_REFUNDED,
    ),
]


@pytest.mark.parametrize(("name", "given_inputs", "expected"), CASES, ids=[c[0] for c in CASES])
def test_each_branch(name: str, given_inputs: OrderStatusInputs, expected: OrderStatus) -> None:
    assert derive_order_status(given_inputs) is expected, name


@settings(database=None, deadline=None, max_examples=300, derandomize=True)
@given(
    method=st.sampled_from(list(PaymentMethod)),
    states=st.lists(st.sampled_from(list(OrderItemStatus)), min_size=1, max_size=6),
    cancelled=st.booleans(),
    paid=st.booleans(),
    cover=st.booleans(),
    refund=st.booleans(),
    owed=st.booleans(),
)
def test_pending_payment_only_for_an_unpaid_online_order(
    method: PaymentMethod,
    states: list[OrderItemStatus],
    cancelled: bool,
    paid: bool,
    cover: bool,
    refund: bool,
    owed: bool,
) -> None:
    over = {"cancelled_at_set": cancelled, "paid": paid, "cover": cover, "refund": refund}
    status = derive_order_status(inputs(method, *states, owed=owed, **over))
    assert status in OrderStatus
    if status is OrderStatus.PENDING_PAYMENT:
        assert method is ONLINE and not paid and not cancelled
