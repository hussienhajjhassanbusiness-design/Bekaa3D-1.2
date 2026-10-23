"""The cash handover rule (VS-029; SRS 9.8.3, BR-055, BR-143)."""

import pytest

from app.ordering.domain.enums import FulfillmentMethod as M
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import PaymentMethod as P
from app.ordering.domain.handover import (
    HandoverRefusal,
    handover_amount_matches,
    handover_refusal,
)

R = HandoverRefusal


@pytest.mark.parametrize(
    ("method", "states"),
    [
        (M.DELIVERY, [S.SHIPPED]),
        (M.DELIVERY, [S.SHIPPED, S.CANCELLED, S.SHIPPED]),
        (M.PICKUP, [S.READY_FOR_PICKUP]),
        (M.PICKUP, [S.CANCELLED, S.READY_FOR_PICKUP]),
    ],
)
def test_every_live_line_ready_is_accepted(method: M, states: list[S]) -> None:
    assert handover_refusal(P.CASH, method, states) is None


@pytest.mark.parametrize(
    ("payment", "method", "states", "reason"),
    [
        (P.ONLINE, M.DELIVERY, [S.SHIPPED], R.NOT_A_CASH_ORDER),
        (P.CASH, None, [S.SHIPPED], R.NOT_A_CASH_ORDER),
        (P.CASH, M.DELIVERY, [], R.NO_LIVE_LINE),
        (P.CASH, M.DELIVERY, [S.CANCELLED, S.CANCELLED], R.NO_LIVE_LINE),
        (P.CASH, M.DELIVERY, [S.DELIVERED, S.SHIPPED], R.ALREADY_RECORDED),
        (P.CASH, M.PICKUP, [S.PICKED_UP], R.ALREADY_RECORDED),
        (P.CASH, M.DELIVERY, [S.SHIPPED, S.READY_TO_SHIP], R.LINES_NOT_READY),
        (P.CASH, M.DELIVERY, [S.RETURNED], R.LINES_NOT_READY),
        (P.CASH, M.DELIVERY, [S.READY_FOR_PICKUP], R.LINES_NOT_READY),
        (P.CASH, M.PICKUP, [S.SHIPPED], R.LINES_NOT_READY),
        (P.CASH, M.PICKUP, [S.IN_PRODUCTION, S.READY_FOR_PICKUP], R.LINES_NOT_READY),
    ],
)
def test_each_refusal_has_its_reason(
    payment: P, method: M | None, states: list[S], reason: R
) -> None:
    assert handover_refusal(payment, method, states) is reason


@pytest.mark.parametrize(
    ("due", "typed", "ok"),
    [(1500, 1500, True), (1500, 1499, False), (1500, 1501, False), (0, 0, False), (1, 0, False)],
)
def test_the_amount_is_exactly_the_live_total_and_above_zero(
    due: int, typed: int, ok: bool
) -> None:
    assert handover_amount_matches(due_cents=due, typed_cents=typed) is ok
