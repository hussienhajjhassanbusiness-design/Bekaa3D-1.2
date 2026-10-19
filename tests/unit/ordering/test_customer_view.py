"""What a customer sees of an order (VS-025 plan Q2, Q3, Q7; SRS 8.9, ADR-024 d8)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.customer_view import (
    can_cancel,
    customer_history,
    customer_line_status,
    customer_lines,
    payment_due,
)
from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.orders import CustomerOrderLine, HistoryEntry

AT = datetime(2026, 10, 19, tzinfo=UTC)
S = OrderItemStatus


def _line(kind: ProductType, status: OrderItemStatus) -> CustomerOrderLine:
    return CustomerOrderLine(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        product_type=kind,
        product_name_snapshot="x",
        image_snapshot=None,
        unit_price_cents=100,
        quantity=1,
        line_total_cents=100,
        currency="USD",
        fulfillment_status=status,
        fulfilled_at=None,
        cancelled_at=None,
    )


def _entry(from_status: str | None, to_status: str) -> HistoryEntry:
    return HistoryEntry(uuid.uuid4(), from_status, to_status, AT)


PHYSICAL, STL = ProductType.PHYSICAL, ProductType.STL


@pytest.mark.parametrize("status", list(OrderItemStatus))
def test_only_in_production_is_masked_as_pending(status: OrderItemStatus) -> None:
    expected = S.PENDING if status is S.IN_PRODUCTION else status
    assert customer_line_status(status) is expected


def test_customer_lines_mask_every_line_and_keep_the_rest() -> None:
    raw = [_line(PHYSICAL, S.IN_PRODUCTION), _line(STL, S.AWAITING_DELIVERY)]
    shown = customer_lines(raw)
    assert [line.fulfillment_status for line in shown] == [S.PENDING, S.AWAITING_DELIVERY]
    assert [line.id for line in shown] == [line.id for line in raw]


def test_history_omits_in_production_and_rewrites_its_exit() -> None:
    entries = [
        _entry(None, "pending"),
        _entry("pending", "in_production"),
        _entry("in_production", "ready_to_ship"),
        _entry("in_production", "pending"),
        _entry("pending_payment", "in_progress"),
    ]
    shown = [(e.from_status, e.to_status) for e in customer_history(entries)]
    assert shown == [
        (None, "pending"),
        ("pending", "ready_to_ship"),
        ("pending_payment", "in_progress"),
    ]


def test_a_reprint_after_a_return_reads_from_returned() -> None:
    """FR-08 return resolution: `returned -> in_production -> shipped`."""
    item = uuid.uuid4()
    entries = [
        HistoryEntry(item, "pending", "in_production", AT),
        HistoryEntry(item, "in_production", "shipped", AT),
        HistoryEntry(item, "shipped", "returned", AT),
        HistoryEntry(item, "returned", "in_production", AT),
        HistoryEntry(item, "in_production", "shipped", AT),
    ]
    shown = [(e.from_status, e.to_status) for e in customer_history(entries)]
    assert shown == [("pending", "shipped"), ("shipped", "returned"), ("returned", "shipped")]


def test_masking_is_per_line() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    entries = [
        HistoryEntry(a, "returned", "in_production", AT),
        HistoryEntry(b, "in_production", "ready_for_pickup", AT),
        HistoryEntry(a, "in_production", "shipped", AT),
    ]
    shown = [(e.from_status, e.to_status) for e in customer_history(entries)]
    assert shown == [("pending", "ready_for_pickup"), ("returned", "shipped")]


def test_history_without_in_production_is_unchanged() -> None:
    entries = [_entry(None, "pending_payment"), _entry("pending", "awaiting_delivery")]
    assert customer_history(entries) == entries


# ------------------------------------------------------------------ payment_due


def test_payment_due_for_an_unpaid_live_cash_order() -> None:
    assert payment_due(
        status=OrderStatus.IN_PROGRESS, payment_method=PaymentMethod.CASH, reached_paid=False
    )


@pytest.mark.parametrize(
    ("status", "method", "reached_paid"),
    [
        (OrderStatus.IN_PROGRESS, PaymentMethod.ONLINE, False),
        (OrderStatus.IN_PROGRESS, PaymentMethod.CASH, True),
        (OrderStatus.CANCELLED, PaymentMethod.CASH, False),
        (OrderStatus.COMPLETED, PaymentMethod.CASH, True),
        (OrderStatus.PENDING_PAYMENT, PaymentMethod.ONLINE, False),
    ],
)
def test_payment_due_is_false_otherwise(
    status: OrderStatus, method: PaymentMethod, reached_paid: bool
) -> None:
    assert not payment_due(status=status, payment_method=method, reached_paid=reached_paid)


# ------------------------------------------------------------------ can_cancel


def _can(**over: Any) -> bool:
    """A paid online mixed order with its physical line pending, then one change."""
    base: dict[str, Any] = {
        "status": OrderStatus.IN_PROGRESS,
        "payment_method": PaymentMethod.ONLINE,
        "reached_paid": True,
        "lines": [_line(PHYSICAL, S.PENDING), _line(STL, S.AWAITING_DELIVERY)],
    }
    return can_cancel(**(base | over))


@pytest.mark.parametrize(
    "over",
    [
        {},
        {"status": OrderStatus.PARTIALLY_REFUNDED},
        {"payment_method": PaymentMethod.CASH, "reached_paid": False},
        {"lines": [_line(PHYSICAL, S.PENDING), _line(PHYSICAL, S.PENDING)]},
        {"lines": [_line(PHYSICAL, S.PENDING), _line(PHYSICAL, S.CANCELLED)]},
    ],
    ids=["paid-online", "partially-refunded", "unpaid-cash", "all-physical", "one-cancelled"],
)
def test_can_cancel_when_every_condition_holds(over: dict[str, Any]) -> None:
    assert _can(**over)


@pytest.mark.parametrize(
    "over",
    [
        {"lines": [_line(STL, S.AWAITING_DELIVERY)]},
        {"lines": []},
        {"reached_paid": False},
        {"status": OrderStatus.PENDING_PAYMENT, "reached_paid": False},
        {"status": OrderStatus.COMPLETED},
        {"status": OrderStatus.CANCELLED},
        {"status": OrderStatus.REFUNDED},
        {"lines": [_line(PHYSICAL, S.PENDING), _line(PHYSICAL, S.IN_PRODUCTION)]},
        {"lines": [_line(PHYSICAL, S.CANCELLED), _line(STL, S.AWAITING_DELIVERY)]},
        {"lines": [_line(PHYSICAL, S.PENDING), _line(PHYSICAL, S.REFUNDED)]},
        {"lines": [_line(PHYSICAL, S.READY_FOR_PICKUP)]},
    ],
    ids=[
        "stl-only",
        "no-lines",
        "online-never-paid",
        "pending-payment",
        "completed",
        "cancelled",
        "refunded",
        "one-in-production",
        "every-physical-cancelled",
        "one-refunded",
        "ready-for-pickup",
    ],
)
def test_can_cancel_is_false_when_one_condition_fails(over: dict[str, Any]) -> None:
    assert not _can(**over)
