"""The refund side of the order projection (VS-030 plan 6.1 U1, U2, U4, U5; ADR-042)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.line_transitions import DELIVERY_EDGES, PICKUP_EDGES, STL_EDGES
from app.ordering.domain.order_status import (
    LineState,
    OrderStatusInputs,
    RefundFacts,
    derive_order_status,
)

S = OrderItemStatus
ONLINE, CASH = PaymentMethod.ONLINE, PaymentMethod.CASH
OWED = RefundFacts(owed=True)
COVERED = RefundFacts(covers_paid=True, present=True)
PRESENT = RefundFacts(present=True)


def status(
    method: PaymentMethod, *states: S, refunds: RefundFacts, paid: bool = True
) -> OrderStatus:
    return derive_order_status(
        OrderStatusInputs(method, False, paid, tuple(LineState(s) for s in states), refunds)
    )


# --- U1 ---------------------------------------------------------------------------------

U1 = [
    ("case-a-owed", (S.REFUNDED,), OWED, OrderStatus.PARTIALLY_REFUNDED),
    ("case-a-after-reissue", (S.REFUNDED,), COVERED, OrderStatus.REFUNDED),
    ("case-b-owed", (S.CANCELLED, S.CANCELLED), OWED, OrderStatus.PARTIALLY_REFUNDED),
    ("case-b-after-reissue", (S.CANCELLED, S.CANCELLED), COVERED, OrderStatus.CANCELLED),
    ("covered", (S.DELIVERED, S.IN_PRODUCTION), COVERED, OrderStatus.REFUNDED),
    ("present", (S.DELIVERED,), PRESENT, OrderStatus.PARTIALLY_REFUNDED),
    ("partial-owed-in-production", (S.IN_PRODUCTION,), OWED, OrderStatus.PARTIALLY_REFUNDED),
    ("owed-beats-completed", (S.DELIVERED, S.PICKED_UP), OWED, OrderStatus.PARTIALLY_REFUNDED),
]


@pytest.mark.parametrize(("name", "states", "refunds", "expected"), U1, ids=[c[0] for c in U1])
def test_u1_refund_rows(
    name: str, states: tuple[S, ...], refunds: RefundFacts, expected: OrderStatus
) -> None:
    for method in PaymentMethod:
        assert status(method, *states, refunds=refunds) is expected, (name, method)


# --- U2 ---------------------------------------------------------------------------------

_facts = st.builds(RefundFacts, st.booleans(), st.booleans(), st.booleans())
_lines = st.lists(st.sampled_from(list(OrderItemStatus)), min_size=1, max_size=6)


@settings(database=None, deadline=None, max_examples=500, derandomize=True)
@given(method=st.sampled_from(list(PaymentMethod)), states=_lines, refunds=_facts)
def test_u2_owed_is_partially_refunded_whenever_paid(
    method: PaymentMethod, states: list[S], refunds: RefundFacts
) -> None:
    derived = status(method, *states, refunds=refunds)
    assert derived in OrderStatus
    if refunds.owed:
        assert derived is OrderStatus.PARTIALLY_REFUNDED


# --- U4: Must-resolve 6, the open-cash count stays status-based ---------------------------


@settings(database=None, deadline=None, max_examples=500, derandomize=True)
@given(states=_lines, refunds=_facts)
def test_u4_p1_an_unpaid_uncancelled_cash_order_is_in_progress(
    states: list[S], refunds: RefundFacts
) -> None:
    if all(s is S.CANCELLED for s in states):
        states = [*states, S.PENDING]
    assert status(CASH, *states, refunds=refunds, paid=False) is OrderStatus.IN_PROGRESS


_handed_over = st.lists(
    st.sampled_from([S.DELIVERED, S.PICKED_UP, S.REFUNDED, S.CANCELLED]), min_size=1, max_size=6
)


@settings(database=None, deadline=None, max_examples=500, derandomize=True)
@given(states=_handed_over, refunds=_facts)
def test_u4_p2_a_paid_cash_order_is_never_in_progress(
    states: list[S], refunds: RefundFacts
) -> None:
    assert status(CASH, *states, refunds=refunds) is not OrderStatus.IN_PROGRESS


# --- U5 ---------------------------------------------------------------------------------


def test_u5_no_edge_leaves_delivered_or_picked_up() -> None:
    """P2 rests on this. A new edge out of either state must revisit
    `SqlCashChecks.open_order_count` and `ix_orders_open_cash_phone` (VS-030 plan 3.1)."""
    for edges in (DELIVERY_EDGES, PICKUP_EDGES, STL_EDGES):
        leaving = {src: dst for src, dst in edges.items() if src in (S.DELIVERED, S.PICKED_UP)}
        assert leaving == {}, (
            f"edge out of a handed-over state; revisit open_order_count: {leaving}"
        )
