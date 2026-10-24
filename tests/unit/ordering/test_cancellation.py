"""Which lines a cancel takes, and BR-144's block rule (VS-031; FR-09, ADR-033 d4)."""

import itertools
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.cancellation import (
    OrderFacts,
    admin_cancels,
    cash_block_reason,
    customer_cancels,
)
from app.ordering.domain.enums import CancelReason as C
from app.ordering.domain.enums import FulfillmentMethod as M
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import OrderStatus as Status
from app.ordering.domain.enums import PaymentMethod as P
from app.ordering.domain.exceptions import InvalidLineTransitionError, OrderNotCancellableError

PHYSICAL, STL = ProductType.PHYSICAL, ProductType.STL


@dataclass(frozen=True)
class Line:
    fulfillment_status: S
    product_type: ProductType = PHYSICAL
    line_total_cents: int = 500
    id: UUID = field(default_factory=uuid4)


def _order(
    status: Status = Status.IN_PROGRESS,
    payment: P = P.ONLINE,
    paid: bool = True,
    method: M | None = M.DELIVERY,
) -> OrderFacts:
    return OrderFacts(status, method, payment, paid)


# --- customer ---------------------------------------------------------------------------


def test_a_customer_cancel_takes_every_pending_physical_line_and_no_stl() -> None:
    lines = [Line(S.PENDING), Line(S.PENDING), Line(S.AWAITING_DELIVERY, STL)]
    cancels = customer_cancels(_order(Status.IN_PROGRESS), lines)
    assert {c.line_id for c in cancels} == {lines[0].id, lines[1].id}
    assert all(c.cancel_reason is None and c.from_status is S.PENDING for c in cancels)


def test_a_line_the_admin_cancelled_neither_blocks_nor_counts() -> None:
    lines = [Line(S.CANCELLED), Line(S.PENDING)]
    cancels = customer_cancels(_order(payment=P.CASH, paid=False), lines)
    assert [c.line_id for c in cancels] == [lines[1].id]
    with pytest.raises(OrderNotCancellableError):
        customer_cancels(_order(payment=P.CASH, paid=False), [Line(S.CANCELLED)])


@pytest.mark.parametrize(
    ("order", "lines"),
    [
        (_order(Status.PENDING_PAYMENT, paid=False), [Line(S.PENDING)]),
        (_order(Status.IN_PROGRESS, method=None), [Line(S.AWAITING_DELIVERY, STL)]),
        (_order(), [Line(S.PENDING), Line(S.IN_PRODUCTION)]),
        (_order(Status.COMPLETED), [Line(S.DELIVERED)]),
        (_order(Status.REFUNDED), [Line(S.PENDING)]),
    ],
    ids=["pending_payment", "stl_only", "one_in_production", "completed", "refunded"],
)
def test_a_customer_cancel_refuses_and_changes_nothing(
    order: OrderFacts, lines: list[Line]
) -> None:
    with pytest.raises(OrderNotCancellableError):
        customer_cancels(order, lines)


# --- administrator ------------------------------------------------------------------------


def test_an_admin_cancel_records_the_reason_only_where_one_is_taken() -> None:
    lines = [Line(S.PENDING), Line(S.READY_TO_SHIP), Line(S.SHIPPED), Line(S.DELIVERED)]
    cancels = admin_cancels(_order(payment=P.CASH, paid=False), lines, C.REFUSED)
    assert [(c.from_status, c.cancel_reason) for c in cancels] == [
        (S.PENDING, None),
        (S.READY_TO_SHIP, C.REFUSED),
    ]


@pytest.mark.parametrize(
    ("order", "lines", "reason", "refusal"),
    [
        (_order(Status.PENDING_PAYMENT, paid=False), [Line(S.PENDING)], None, "payment_required"),
        (_order(), [Line(S.SHIPPED), Line(S.DELIVERED)], None, "no_cancellable_line"),
        (_order(method=None), [Line(S.AWAITING_DELIVERY, STL)], None, "no_cancellable_line"),
        (_order(), [Line(S.READY_TO_SHIP)], None, "cancel_reason_required"),
        (_order(), [Line(S.READY_TO_SHIP)], C.NO_SHOW, "cancel_reason_not_allowed"),
        (_order(), [Line(S.PENDING)], C.OTHER, "cancel_reason_not_allowed"),
    ],
)
def test_an_admin_cancel_refuses_with_its_stable_reason(
    order: OrderFacts, lines: list[Line], reason: C | None, refusal: str
) -> None:
    with pytest.raises(InvalidLineTransitionError) as caught:
        admin_cancels(order, lines, reason)
    assert caught.value.reason == refusal


def test_no_show_is_taken_for_a_pickup_line() -> None:
    order = _order(payment=P.CASH, paid=False, method=M.PICKUP)
    (cancel,) = admin_cancels(order, [Line(S.READY_FOR_PICKUP)], C.NO_SHOW)
    assert cancel.cancel_reason is C.NO_SHOW


# --- BR-144 -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        ([(S.CANCELLED, C.REFUSED)], C.REFUSED),
        ([(S.CANCELLED, C.NO_SHOW)], C.NO_SHOW),
        ([(S.CANCELLED, C.NO_SHOW), (S.CANCELLED, C.REFUSED)], C.REFUSED),
        ([(S.CANCELLED, None), (S.CANCELLED, C.REFUSED)], C.REFUSED),
        ([(S.CANCELLED, C.REFUSED), (S.CANCELLED, C.OTHER)], None),
        ([(S.CANCELLED, C.REFUSED), (S.SHIPPED, None)], None),
        ([(S.CANCELLED, None)], None),
        ([(S.CANCELLED, C.OTHER)], None),
    ],
)
def test_the_block_rule_reads_every_line(
    after: list[tuple[S, C | None]], expected: C | None
) -> None:
    assert cash_block_reason(P.CASH, after) is expected


def test_the_outcome_does_not_depend_on_cancel_order() -> None:
    reasons = [C.REFUSED, C.OTHER, None, C.NO_SHOW]
    for a, b in itertools.product(reasons, reasons):
        first = cash_block_reason(P.CASH, [(S.CANCELLED, a), (S.CANCELLED, b)])
        assert first is cash_block_reason(P.CASH, [(S.CANCELLED, b), (S.CANCELLED, a)])


def test_an_online_order_never_blocks() -> None:
    assert cash_block_reason(P.ONLINE, [(S.CANCELLED, C.REFUSED)]) is None
