"""The line edge table (VS-023b STL, VS-029 physical; SRS 20.3-20.5, BR-148, ADR-024 d5)."""

import itertools

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import FulfillmentMethod as M
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import PaymentMethod as P
from app.ordering.domain.line_transitions import (
    LineContext,
    TransitionRefusal,
    available_targets,
    line_transition_refusal,
)

R = TransitionRefusal
STL = LineContext(ProductType.STL, None, P.ONLINE, True)


def _physical(method: M, payment: P, paid: bool) -> LineContext:
    return LineContext(ProductType.PHYSICAL, method, payment, paid)


def _legal(ctx: LineContext) -> set[tuple[S, S]]:
    return {
        (cur, tgt)
        for cur, tgt in itertools.product(S, S)
        if line_transition_refusal(ctx, cur, tgt) is None
    }


DELIVERY = {
    (S.PENDING, S.IN_PRODUCTION),
    (S.IN_PRODUCTION, S.READY_TO_SHIP),
    (S.READY_TO_SHIP, S.SHIPPED),
}
PICKUP = {(S.PENDING, S.IN_PRODUCTION), (S.IN_PRODUCTION, S.READY_FOR_PICKUP)}


def test_stl_has_one_edge_whatever_the_payment_flag() -> None:
    assert _legal(STL) == {(S.AWAITING_DELIVERY, S.DELIVERED)}


def test_paid_online_delivery_and_pickup_edges() -> None:
    delivered = {(S.SHIPPED, S.DELIVERED)}
    assert _legal(_physical(M.DELIVERY, P.ONLINE, True)) == DELIVERY | delivered
    picked_up = {(S.READY_FOR_PICKUP, S.PICKED_UP)}
    assert _legal(_physical(M.PICKUP, P.ONLINE, True)) == PICKUP | picked_up


@pytest.mark.parametrize("paid", [False, True])
def test_cash_reaches_delivered_and_picked_up_only_through_the_handover(paid: bool) -> None:
    assert _legal(_physical(M.DELIVERY, P.CASH, paid)) == DELIVERY
    assert _legal(_physical(M.PICKUP, P.CASH, paid)) == PICKUP
    for method, cur, tgt in [
        (M.DELIVERY, S.SHIPPED, S.DELIVERED),
        (M.PICKUP, S.READY_FOR_PICKUP, S.PICKED_UP),
    ]:
        ctx = _physical(method, P.CASH, paid)
        assert line_transition_refusal(ctx, cur, tgt) is R.CASH_HANDOVER_REQUIRED


@pytest.mark.parametrize("method", list(M))
def test_an_unpaid_online_order_refuses_every_physical_edge(method: M) -> None:
    ctx = _physical(method, P.ONLINE, False)
    assert _legal(ctx) == set()
    assert {line_transition_refusal(ctx, c, t) for c, t in itertools.product(S, S)} == {
        R.PAYMENT_REQUIRED
    }


def test_a_delivery_line_cannot_use_pickup_edges_and_the_reverse() -> None:
    delivery, pickup = _physical(M.DELIVERY, P.ONLINE, True), _physical(M.PICKUP, P.ONLINE, True)
    assert line_transition_refusal(delivery, S.IN_PRODUCTION, S.READY_FOR_PICKUP) is (
        R.NOT_A_LEGAL_EDGE
    )
    assert line_transition_refusal(pickup, S.IN_PRODUCTION, S.READY_TO_SHIP) is R.NOT_A_LEGAL_EDGE


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.READY_TO_SHIP),  # skipped
        (S.PENDING, S.DELIVERED),
        (S.IN_PRODUCTION, S.IN_PRODUCTION),  # the loser of two administrators
        (S.SHIPPED, S.RETURNED),  # VS-031
        (S.PENDING, S.CANCELLED),  # VS-031
        (S.DELIVERED, S.REFUNDED),  # VS-030
        (S.DELIVERED, S.SHIPPED),
    ],
)
def test_skipped_backward_and_later_slice_edges_are_refused(current: S, target: S) -> None:
    ctx = _physical(M.DELIVERY, P.ONLINE, True)
    assert line_transition_refusal(ctx, current, target) is R.NOT_A_LEGAL_EDGE


@pytest.mark.parametrize("current", [S.CANCELLED, S.REFUNDED])
def test_a_closed_physical_line_says_so(current: S) -> None:
    ctx = _physical(M.PICKUP, P.CASH, False)
    assert line_transition_refusal(ctx, current, S.IN_PRODUCTION) is R.LINE_CLOSED


@pytest.mark.parametrize(
    ("current", "reason"),
    [
        (S.DELIVERED, R.ALREADY_DELIVERED),
        (S.REFUNDED, R.LINE_CLOSED),
        (S.CANCELLED, R.LINE_CLOSED),
        (S.PENDING, R.NOT_AWAITING_DELIVERY),
    ],
)
def test_every_stl_refusal_keeps_its_stable_reason(current: S, reason: R) -> None:
    assert line_transition_refusal(STL, current, S.DELIVERED) is reason


@pytest.mark.parametrize("target", [t for t in S if t is not S.DELIVERED])
def test_an_stl_line_takes_no_physical_target(target: S) -> None:
    assert line_transition_refusal(STL, S.AWAITING_DELIVERY, target) is R.NOT_A_LEGAL_EDGE


CONTEXTS = [STL] + [_physical(m, p, paid) for m, p, paid in itertools.product(M, P, [False, True])]


@pytest.mark.parametrize("ctx", CONTEXTS)
@pytest.mark.parametrize("current", list(S))
def test_available_targets_are_exactly_the_accepted_targets(ctx: LineContext, current: S) -> None:
    accepted = {t for t in S if line_transition_refusal(ctx, current, t) is None}
    assert set(available_targets(ctx, current)) == accepted
