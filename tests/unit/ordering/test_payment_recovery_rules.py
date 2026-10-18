"""T1, the hold deadline, the manual release refusals and the shared provider choice
(VS-024 plan 3.1, 2.5, 6.1; Revision 2 Q6, Q7)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.checkout_rules import choose_provider
from app.ordering.domain.enums import (
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.exceptions import PaymentMethodNotAllowedError
from app.ordering.domain.orders import Order, OrderLine
from app.ordering.domain.payment_recovery import (
    ReleaseRefusal,
    RetryRefusal,
    can_retry_payment,
    hold_deadline,
    manual_release_available_at,
    manual_release_refusal,
    retry_refusal,
)

PLACED = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
HOLD = timedelta(minutes=30)
GRACE = timedelta(hours=24)
ORDER = Order(
    id=uuid.uuid4(),
    order_number="B3D-TEST0001",
    user_id=uuid.uuid4(),
    customer_email_snapshot="buyer@example.com",
    source=OrderSource.CART,
    status=OrderStatus.PENDING_PAYMENT,
    fulfillment_method=None,
    payment_method=PaymentMethod.ONLINE,
    subtotal_cents=1000,
    tax_cents=0,
    total_cents=1000,
    currency="USD",
    placed_at=PLACED,
    cancelled_at=None,
)
LINE = OrderLine(
    id=uuid.uuid4(),
    order_id=ORDER.id,
    user_id=ORDER.user_id,
    product_id=uuid.uuid4(),
    product_type=ProductType.STL,
    product_name_snapshot="Dragon",
    unit_price_cents=1000,
    quantity=1,
    line_total_cents=1000,
    currency="USD",
    fulfillment_status=OrderItemStatus.PENDING,
)


def retry(order: Order = ORDER, line: OrderLine = LINE, *, now: datetime) -> RetryRefusal | None:
    return retry_refusal(order, [line], now=now, hold=HOLD)


def test_a_payable_order_inside_its_hold_may_retry() -> None:
    assert retry(now=PLACED + HOLD - timedelta(seconds=1)) is None
    assert can_retry_payment(ORDER, [LINE], now=PLACED, hold=HOLD)


def test_the_hold_boundary_itself_is_refused() -> None:
    assert retry(now=PLACED + HOLD) is RetryRefusal.CHECKOUT_HOLD_EXPIRED
    assert not can_retry_payment(ORDER, [LINE], now=PLACED + HOLD, hold=HOLD)


def test_t1_first_match_wins() -> None:
    late = PLACED + HOLD * 3
    cash_cancelled = replace(ORDER, payment_method=PaymentMethod.CASH, cancelled_at=PLACED)
    assert retry(cash_cancelled, now=late) is RetryRefusal.CASH_ORDER
    cancelled = replace(ORDER, status=OrderStatus.CANCELLED, cancelled_at=PLACED)
    assert retry(cancelled, now=late) is RetryRefusal.ORDER_CANCELLED
    paid = replace(ORDER, status=OrderStatus.IN_PROGRESS)
    assert retry(paid, now=late) is RetryRefusal.ORDER_NOT_PAYABLE


@pytest.mark.parametrize("status", [s for s in OrderItemStatus if s is not OrderItemStatus.PENDING])
def test_any_line_not_pending_makes_the_order_unpayable(status: OrderItemStatus) -> None:
    moved = replace(LINE, fulfillment_status=status)
    assert retry(line=moved, now=PLACED) is RetryRefusal.ORDER_NOT_PAYABLE


@pytest.mark.parametrize("status", [s for s in OrderStatus if s is not OrderStatus.PENDING_PAYMENT])
def test_every_other_order_status_is_unpayable(status: OrderStatus) -> None:
    assert retry(replace(ORDER, status=status), now=PLACED) is RetryRefusal.ORDER_NOT_PAYABLE


def test_the_deadline_runs_from_the_later_of_placement_and_the_latest_attempt() -> None:
    assert hold_deadline(PLACED, None, HOLD) == PLACED + HOLD
    assert hold_deadline(PLACED, PLACED - HOLD, HOLD) == PLACED + HOLD
    retried = PLACED + HOLD - timedelta(seconds=1)
    assert hold_deadline(PLACED, retried, HOLD) == retried + HOLD


def test_the_manual_release_waits_for_the_grace_unless_early() -> None:
    deadline = PLACED + HOLD
    assert manual_release_available_at(deadline, GRACE, early=False) == deadline + GRACE
    assert manual_release_available_at(deadline, GRACE, early=True) == deadline


def release(
    order: Order = ORDER,
    line: OrderLine = LINE,
    *,
    now: datetime,
    events: int = 0,
    reviewed: bool = False,
) -> ReleaseRefusal | None:
    return manual_release_refusal(
        order,
        [line],
        now=now,
        available_at=PLACED + HOLD + GRACE,
        unprocessed_events=events,
        events_reviewed=reviewed,
    )


def test_the_release_opens_exactly_at_the_grace() -> None:
    opens = PLACED + HOLD + GRACE
    assert release(now=opens - timedelta(seconds=1)) is ReleaseRefusal.GRACE_NOT_ELAPSED
    assert release(now=opens) is None


def test_unprocessed_events_need_an_explicit_review() -> None:
    opens = PLACED + HOLD + GRACE
    assert release(now=opens, events=2) is ReleaseRefusal.UNPROCESSED_EVENTS
    assert release(now=opens, events=2, reviewed=True) is None


def test_release_first_match_wins() -> None:
    late = PLACED + HOLD + GRACE * 2
    cash = replace(ORDER, payment_method=PaymentMethod.CASH)
    assert release(cash, now=late, events=1) is ReleaseRefusal.CASH_ORDER
    cancelled = replace(ORDER, status=OrderStatus.CANCELLED, cancelled_at=PLACED)
    assert release(cancelled, now=late) is ReleaseRefusal.ORDER_CANCELLED
    paid = replace(ORDER, status=OrderStatus.IN_PROGRESS)
    assert release(paid, now=PLACED, events=1) is ReleaseRefusal.ORDER_NOT_PAYABLE
    shipped = replace(LINE, fulfillment_status=OrderItemStatus.AWAITING_DELIVERY)
    assert release(line=shipped, now=late) is ReleaseRefusal.ORDER_NOT_PAYABLE


@pytest.mark.parametrize(
    ("requested", "configured", "previous", "chosen"),
    [
        ("mock", {"mock"}, None, "mock"),
        (None, {"mock"}, None, "mock"),
        (None, {"mock", "whish"}, "whish", "whish"),
        (None, {"mock"}, "whish", "mock"),
        ("whish", {"mock", "whish"}, "mock", "whish"),
    ],
)
def test_choose_provider(
    requested: str | None, configured: set[str], previous: str | None, chosen: str
) -> None:
    assert choose_provider(requested, frozenset(configured), previous) == chosen


@pytest.mark.parametrize(
    ("requested", "configured", "previous", "reason"),
    [
        ("whish", {"mock"}, None, "provider_not_configured"),
        ("whish", {"mock"}, "whish", "provider_not_configured"),
        (None, {"mock", "whish"}, None, "provider_required"),
        (None, {"mock", "whish"}, "card", "provider_required"),
        (None, set(), None, "provider_required"),
    ],
)
def test_choose_provider_refusals(
    requested: str | None, configured: set[str], previous: str | None, reason: str
) -> None:
    with pytest.raises(PaymentMethodNotAllowedError) as caught:
        choose_provider(requested, frozenset(configured), previous)
    assert caught.value.reason == reason
