"""One notice per order per visible step, on the last live physical line (ADR-040 d2)."""

import pytest

from app.ordering.domain.enums import FulfillmentMethod as M
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.fulfillment_steps import step_reached


def _sent_while_moving(method: M, path: list[S], lines: int) -> list[tuple[int, S]]:
    """Move each line through `path` one at a time; record (line, step) when a notice fires."""
    states = [path[0]] * lines
    sent = []
    for step in path[1:]:
        for index in range(lines):
            states[index] = step
            if step_reached(method, step, states):
                sent.append((index, step))
    return sent


def test_a_three_line_delivery_order_hears_once_per_step_on_the_last_line() -> None:
    path = [S.PENDING, S.IN_PRODUCTION, S.READY_TO_SHIP, S.SHIPPED, S.DELIVERED]
    assert _sent_while_moving(M.DELIVERY, path, 3) == [
        (2, S.READY_TO_SHIP),
        (2, S.SHIPPED),
        (2, S.DELIVERED),
    ]


def test_a_three_line_pickup_order_hears_once_per_step_on_the_last_line() -> None:
    path = [S.PENDING, S.IN_PRODUCTION, S.READY_FOR_PICKUP, S.PICKED_UP]
    assert _sent_while_moving(M.PICKUP, path, 3) == [(2, S.READY_FOR_PICKUP), (2, S.PICKED_UP)]


def test_a_line_already_past_the_step_counts_as_having_reached_it() -> None:
    assert step_reached(M.DELIVERY, S.READY_TO_SHIP, [S.SHIPPED, S.READY_TO_SHIP])
    assert step_reached(M.DELIVERY, S.SHIPPED, [S.RETURNED, S.SHIPPED])


def test_a_line_left_behind_holds_the_notice_back() -> None:
    assert not step_reached(M.DELIVERY, S.SHIPPED, [S.SHIPPED, S.READY_TO_SHIP])
    assert not step_reached(M.PICKUP, S.READY_FOR_PICKUP, [S.READY_FOR_PICKUP, S.IN_PRODUCTION])


def test_cancelled_and_refunded_lines_are_not_waited_for() -> None:
    assert step_reached(M.DELIVERY, S.SHIPPED, [S.SHIPPED, S.CANCELLED, S.REFUNDED])
    assert not step_reached(M.DELIVERY, S.SHIPPED, [S.CANCELLED])


@pytest.mark.parametrize("step", [S.PENDING, S.IN_PRODUCTION, S.RETURNED, S.CANCELLED])
def test_internal_and_non_steps_never_notify(step: S) -> None:
    assert not step_reached(M.DELIVERY, step, [step])
    assert not step_reached(M.PICKUP, step, [step])


def test_a_step_from_the_other_method_never_notifies() -> None:
    assert not step_reached(M.PICKUP, S.SHIPPED, [S.SHIPPED])
    assert not step_reached(M.DELIVERY, S.READY_FOR_PICKUP, [S.READY_FOR_PICKUP])
    assert not step_reached(None, S.SHIPPED, [S.SHIPPED])
