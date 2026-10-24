"""The line edge table (VS-023b STL, VS-029 physical, VS-031 cancel and return; SRS
20.3-20.5, BR-144, BR-148, ADR-024 d5)."""

import itertools

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import CancelReason as C
from app.ordering.domain.enums import FulfillmentMethod as M
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import PaymentMethod as P
from app.ordering.domain.line_transitions import (
    LineContext,
    TransitionRefusal,
    available_actions,
    available_targets,
    line_transition_refusal,
)

R = TransitionRefusal
STL = LineContext(ProductType.STL, None, P.ONLINE, True, 500)
REASONS: list[C | None] = [None, *C]


def _physical(method: M, payment: P, paid: bool, total: int = 500) -> LineContext:
    return LineContext(ProductType.PHYSICAL, method, payment, paid, total)


def _accepts(ctx: LineContext, cur: S, tgt: S) -> set[C | None]:
    return {r for r in REASONS if line_transition_refusal(ctx, cur, tgt, r) is None}


def _legal(ctx: LineContext) -> set[tuple[S, S]]:
    return {(cur, tgt) for cur, tgt in itertools.product(S, S) if _accepts(ctx, cur, tgt)}


DELIVERY = {
    (S.PENDING, S.IN_PRODUCTION),
    (S.IN_PRODUCTION, S.READY_TO_SHIP),
    (S.READY_TO_SHIP, S.SHIPPED),
    (S.PENDING, S.CANCELLED),
    (S.IN_PRODUCTION, S.CANCELLED),
    (S.READY_TO_SHIP, S.CANCELLED),
    (S.SHIPPED, S.RETURNED),
    (S.RETURNED, S.SHIPPED),
    (S.RETURNED, S.IN_PRODUCTION),
}
PICKUP = {
    (S.PENDING, S.IN_PRODUCTION),
    (S.IN_PRODUCTION, S.READY_FOR_PICKUP),
    (S.PENDING, S.CANCELLED),
    (S.IN_PRODUCTION, S.CANCELLED),
    (S.READY_FOR_PICKUP, S.CANCELLED),
}


def test_stl_has_one_edge_whatever_the_payment_flag() -> None:
    assert _legal(STL) == {(S.AWAITING_DELIVERY, S.DELIVERED)}


def test_paid_online_delivery_and_pickup_edges() -> None:
    delivered = {(S.SHIPPED, S.DELIVERED)}
    assert _legal(_physical(M.DELIVERY, P.ONLINE, True)) == DELIVERY | delivered
    picked_up = {(S.READY_FOR_PICKUP, S.PICKED_UP)}
    assert _legal(_physical(M.PICKUP, P.ONLINE, True)) == PICKUP | picked_up


@pytest.mark.parametrize("paid", [False, True])
def test_cash_reaches_delivered_and_picked_up_only_through_the_handover(paid: bool) -> None:
    unpaid_return_cancel = set() if paid else {(S.RETURNED, S.CANCELLED)}
    assert _legal(_physical(M.DELIVERY, P.CASH, paid)) == DELIVERY | unpaid_return_cancel
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
        (S.DELIVERED, S.REFUNDED),  # through the refund endpoint (VS-030)
        (S.RETURNED, S.REFUNDED),  # likewise (VS-031 Q2)
        (S.DELIVERED, S.SHIPPED),
        (S.DELIVERED, S.RETURNED),
        (S.RETURNED, S.DELIVERED),
        (S.SHIPPED, S.CANCELLED),  # a paid line is returned, then refunded
        (S.RETURNED, S.CANCELLED),  # never on a paid online order
    ],
)
def test_skipped_backward_and_later_slice_edges_are_refused(current: S, target: S) -> None:
    ctx = _physical(M.DELIVERY, P.ONLINE, True)
    assert _accepts(ctx, current, target) == set()
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


CONTEXTS = [STL] + [
    _physical(m, p, paid, total)
    for m, p, paid, total in itertools.product(M, P, [False, True], [0, 500])
]


@pytest.mark.parametrize("ctx", CONTEXTS)
@pytest.mark.parametrize("current", list(S))
def test_available_actions_are_exactly_the_accepted_edges_and_reasons(
    ctx: LineContext, current: S
) -> None:
    accepted = {t: _accepts(ctx, current, t) for t in S if _accepts(ctx, current, t)}
    actions = dict(available_actions(ctx, current))
    assert set(available_targets(ctx, current)) == set(actions) == set(accepted)
    for target, reasons in actions.items():
        assert set(reasons) == accepted[target] - {None}
        assert (None in accepted[target]) is (reasons == ())


# --- VS-031: the cancel and return edges ---------------------------------------------------


@pytest.mark.parametrize("total", [0, 500])
def test_a_shipped_unpaid_cash_line_is_cancelled_only_at_zero_with_other(total: int) -> None:
    ctx = _physical(M.DELIVERY, P.CASH, False, total)
    assert _accepts(ctx, S.SHIPPED, S.CANCELLED) == ({C.OTHER} if total == 0 else set())


@pytest.mark.parametrize(
    ("method", "current", "reasons"),
    [
        (M.DELIVERY, S.PENDING, {None}),
        (M.DELIVERY, S.IN_PRODUCTION, {None}),
        (M.DELIVERY, S.READY_TO_SHIP, {C.REFUSED, C.OTHER}),
        (M.DELIVERY, S.RETURNED, {C.REFUSED, C.OTHER}),
        (M.PICKUP, S.PENDING, {None}),
        (M.PICKUP, S.IN_PRODUCTION, {None}),
        (M.PICKUP, S.READY_FOR_PICKUP, {C.REFUSED, C.NO_SHOW, C.OTHER}),
    ],
)
def test_each_cancel_takes_exactly_its_reasons(
    method: M, current: S, reasons: set[C | None]
) -> None:
    assert _accepts(_physical(method, P.CASH, False), current, S.CANCELLED) == reasons


@pytest.mark.parametrize("current", [S.READY_TO_SHIP, S.RETURNED])
def test_no_show_is_refused_outside_pickup(current: S) -> None:
    ctx = _physical(M.DELIVERY, P.CASH, False)
    refusal = line_transition_refusal(ctx, current, S.CANCELLED, C.NO_SHOW)
    assert refusal is R.CANCEL_REASON_NOT_ALLOWED
    assert line_transition_refusal(ctx, current, S.CANCELLED) is R.CANCEL_REASON_REQUIRED


def test_a_reason_on_an_edge_that_takes_none_is_refused() -> None:
    ctx = _physical(M.DELIVERY, P.ONLINE, True)
    for current, target in [(S.PENDING, S.CANCELLED), (S.SHIPPED, S.RETURNED)]:
        refusal = line_transition_refusal(ctx, current, target, C.OTHER)
        assert refusal is R.CANCEL_REASON_NOT_ALLOWED


def test_returned_cancel_is_for_an_unpaid_cash_line_only() -> None:
    assert _accepts(_physical(M.DELIVERY, P.ONLINE, True), S.RETURNED, S.CANCELLED) == set()
    assert _accepts(_physical(M.DELIVERY, P.CASH, True), S.RETURNED, S.CANCELLED) == set()
    unpaid = _physical(M.DELIVERY, P.CASH, False)
    assert _accepts(unpaid, S.RETURNED, S.CANCELLED) == {C.REFUSED, C.OTHER}


@pytest.mark.parametrize("reason", REASONS)
def test_an_stl_line_is_never_cancelled(reason: C | None) -> None:
    for current in S:
        assert line_transition_refusal(STL, current, S.CANCELLED, reason) is R.NOT_A_LEGAL_EDGE
