"""The SRS 7.4 matrix, dispatch estimate, cash limits and amount due (VS-028 plan 6.1)."""

from datetime import UTC, datetime
from itertools import product
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.cash import amount_due_cents, cash_limits, cash_precheck
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.exceptions import (
    CashLimitReachedError,
    InvalidFulfillmentError,
    PaymentMethodNotAllowedError,
)
from app.ordering.domain.fulfillment import (
    Fulfillment,
    dispatch_days,
    estimated_dispatch_at,
    resolve_fulfillment,
)
from app.ordering.domain.order_status import LineState, OrderStatusInputs, derive_order_status
from app.ordering.domain.orders import NewOrderLine

P, S = ProductType.PHYSICAL, ProductType.STL
DELIVERY, PICKUP = FulfillmentMethod.DELIVERY, FulfillmentMethod.PICKUP
ONLINE, CASH = PaymentMethod.ONLINE, PaymentMethod.CASH
ADDRESS = uuid4()
PHONE = "+96171999888"


def resolve(
    types: list[ProductType],
    pay: PaymentMethod,
    method: FulfillmentMethod | None = None,
    address: UUID | None = None,
    phone: str | None = None,
) -> Fulfillment:
    return resolve_fulfillment(
        types, payment_method=pay, method=method, address_id=address, contact_phone=phone
    )


@pytest.mark.parametrize("pay", [ONLINE, CASH])
def test_a_physical_delivery_and_a_physical_pickup_resolve_for_both_methods(
    pay: PaymentMethod,
) -> None:
    assert resolve([P, P], pay, DELIVERY, ADDRESS) == Fulfillment(DELIVERY, ADDRESS, None)
    assert resolve([P], pay, PICKUP, None, PHONE) == Fulfillment(PICKUP, None, PHONE)


def test_an_stl_only_cart_takes_no_fulfillment_and_pays_online() -> None:
    assert resolve([S], ONLINE) == Fulfillment(None, None, None)
    with pytest.raises(PaymentMethodNotAllowedError) as caught:
        resolve([S], CASH)
    assert caught.value.reason == "cash_requires_physical"


@pytest.mark.parametrize("pay", [ONLINE, CASH])
@pytest.mark.parametrize("field", ["method", "address", "phone"])
def test_an_stl_only_cart_with_any_fulfillment_field_is_invalid(
    pay: PaymentMethod, field: str
) -> None:
    given: dict[str, Any] = {"method": DELIVERY, "address": ADDRESS, "phone": PHONE}
    with pytest.raises(InvalidFulfillmentError):
        resolve([S], pay, **{field: given[field]})


@pytest.mark.parametrize("method", [DELIVERY, PICKUP])
def test_a_mixed_cart_is_online_only(method: FulfillmentMethod) -> None:
    address, phone = (ADDRESS, None) if method is DELIVERY else (None, PHONE)
    assert resolve([S, P], ONLINE, method, address, phone).method is method
    with pytest.raises(PaymentMethodNotAllowedError) as caught:
        resolve([S, P], CASH, method, address, phone)
    assert caught.value.reason == "cash_requires_physical"


@pytest.mark.parametrize(
    ("method", "address", "phone"),
    [
        (None, None, None),
        (DELIVERY, None, None),
        (DELIVERY, ADDRESS, PHONE),
        (PICKUP, None, None),
        (PICKUP, ADDRESS, PHONE),
        (PICKUP, ADDRESS, None),
        (None, ADDRESS, None),
        (None, None, PHONE),
    ],
)
@pytest.mark.parametrize("pay", [ONLINE, CASH])
def test_every_invalid_physical_combination_is_refused(
    pay: PaymentMethod, method: FulfillmentMethod | None, address: UUID | None, phone: str | None
) -> None:
    with pytest.raises(InvalidFulfillmentError):
        resolve([P], pay, method, address, phone)


def test_a_mixed_cart_whose_stl_was_dropped_is_physical_and_may_pay_cash() -> None:
    """The matrix runs on the kept lines (Q13): the caller passes the kept types only."""
    assert resolve([P], CASH, DELIVERY, ADDRESS).method is DELIVERY


def line(qty: int, lead: int | None, batch: int | None, kind: ProductType = P) -> NewOrderLine:
    return NewOrderLine(
        product_id=uuid4(),
        product_type=kind,
        product_name_snapshot="x",
        image_snapshot=None,
        unit_price_cents=100,
        quantity=qty,
        line_total_cents=100 * qty,
        currency="USD",
        lead_time_days_snapshot=lead,
        batch_size_snapshot=batch,
    )


def test_dispatch_days() -> None:
    assert dispatch_days([line(10, 2, 4)]) == 6
    assert dispatch_days([line(8, 3, 4)]) == 6  # an exact multiple of the batch: 2 batches
    assert dispatch_days([line(1, 0, 1)]) == 0
    assert dispatch_days([line(10, 2, 4), line(1, 5, 10)]) == 6
    assert dispatch_days([line(1, 9, 1), line(1, None, None, S)]) == 9
    assert dispatch_days([line(1, None, None, S)]) is None


def test_the_estimate_is_calendar_days_after_placement() -> None:
    placed = datetime(2026, 10, 22, 10, tzinfo=UTC)
    assert estimated_dispatch_at(placed, 6) == datetime(2026, 10, 28, 10, tzinfo=UTC)
    assert estimated_dispatch_at(placed, None) is None


def test_cash_precheck_reasons_and_precedence() -> None:
    def reason(lines: list[NewOrderLine], total: int, enabled: bool) -> str:
        with pytest.raises(PaymentMethodNotAllowedError) as caught:
            cash_precheck(lines, total, enabled=enabled)
        return caught.value.reason

    assert reason([line(1, None, None, S)], 0, False) == "cash_requires_physical"
    assert reason([line(1, 1, 1)], 0, False) == "cash_disabled"
    assert reason([line(1, 1, 1)], 0, True) == "zero_total"
    cash_precheck([line(1, 1, 1)], 1, enabled=True)


LIMITS: dict[str, Any] = {
    "blocked": False,
    "open_orders": 0,
    "max_open": 1,
    "total_cents": 100,
    "max_total": 100,
}


def refused(**over: Any) -> str:
    with pytest.raises((PaymentMethodNotAllowedError, CashLimitReachedError)) as caught:
        cash_limits(**(LIMITS | over))
    return str(caught.value.reason)


def test_cash_limits_boundaries() -> None:
    cash_limits(**LIMITS)
    cash_limits(**(LIMITS | {"open_orders": 2, "max_open": 3}))  # open == max - 1 passes
    assert refused(open_orders=1) == "open_orders"  # open == max refuses
    assert refused(total_cents=101) == "order_total"  # total == max passed above
    assert refused(blocked=True) == "cash_blocked"


def test_cash_limits_precedence_is_blocked_then_open_orders_then_total() -> None:
    everything: dict[str, Any] = {"blocked": True, "open_orders": 5, "total_cents": 999}
    assert refused(**everything) == "cash_blocked"
    assert refused(**(everything | {"blocked": False})) == "open_orders"
    assert refused(**(everything | {"blocked": False, "open_orders": 0})) == "order_total"


class _Line:
    def __init__(self, cents: int, status: OrderItemStatus) -> None:
        self.line_total_cents, self.fulfillment_status = cents, status


def test_amount_due_excludes_cancelled_lines() -> None:
    lines = [
        _Line(500, OrderItemStatus.PENDING),
        _Line(300, OrderItemStatus.CANCELLED),
        _Line(200, OrderItemStatus.SHIPPED),
    ]
    assert amount_due_cents(lines) == 700
    assert amount_due_cents([]) == 0


TERMINAL = [
    OrderItemStatus.DELIVERED,
    OrderItemStatus.PICKED_UP,
    OrderItemStatus.REFUNDED,
    OrderItemStatus.CANCELLED,
]


@pytest.mark.parametrize("size", [1, 2, 3])
def test_a_paid_cash_order_with_only_terminal_lines_never_derives_in_progress(size: int) -> None:
    """D8: `in_progress` on a cash order means unpaid; no edge leaves a terminal state."""
    for combo in product(TERMINAL, repeat=size):
        for refund_present in (False, True):
            status = derive_order_status(
                OrderStatusInputs(
                    CASH,
                    cancelled_at_set=False,
                    payment_reached_paid=True,
                    lines=tuple(LineState(s) for s in combo),
                    refund_present=refund_present,
                )
            )
            assert status is not OrderStatus.IN_PROGRESS, combo


def test_an_unpaid_cash_order_is_in_progress_until_every_line_is_cancelled() -> None:
    def derived(status: OrderItemStatus) -> OrderStatus:
        return derive_order_status(
            OrderStatusInputs(
                CASH,
                cancelled_at_set=False,
                payment_reached_paid=False,
                lines=(LineState(status),),
            )
        )

    assert derived(OrderItemStatus.PENDING) is OrderStatus.IN_PROGRESS
    assert derived(OrderItemStatus.CANCELLED) is OrderStatus.CANCELLED
