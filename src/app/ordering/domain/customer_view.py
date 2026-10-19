"""What a customer may see of an order (VS-025; SRS 8.9, ADR-024 d8). Pure.
`in_production` ("start printing") is internal: shown as `pending`, absent from history."""

from collections.abc import Iterable
from dataclasses import replace

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.orders import CustomerOrderLine, HistoryEntry

HIDDEN_STATUS = OrderItemStatus.IN_PRODUCTION
CANCELLABLE_ORDER_STATUSES = frozenset({OrderStatus.IN_PROGRESS, OrderStatus.PARTIALLY_REFUNDED})


def customer_line_status(status: OrderItemStatus) -> OrderItemStatus:
    return OrderItemStatus.PENDING if status is HIDDEN_STATUS else status


def customer_lines(lines: Iterable[CustomerOrderLine]) -> list[CustomerOrderLine]:
    return [
        replace(line, fulfillment_status=customer_line_status(line.fulfillment_status))
        for line in lines
    ]


def customer_history(entries: Iterable[HistoryEntry]) -> list[HistoryEntry]:
    """Entries into `in_production` are dropped; one out of it reads as from `pending`,
    and an entry that masking turns into `pending -> pending` is dropped too."""
    shown = []
    for entry in entries:
        if entry.to_status == HIDDEN_STATUS.value:
            continue
        if entry.from_status == HIDDEN_STATUS.value:
            entry = replace(entry, from_status=OrderItemStatus.PENDING.value)
        if entry.from_status != entry.to_status:
            shown.append(entry)
    return shown


def payment_due(*, status: OrderStatus, payment_method: PaymentMethod, reached_paid: bool) -> bool:
    """An unpaid, live cash order (SRS 20.2; VS-025 plan Q2)."""
    return (
        payment_method is PaymentMethod.CASH
        and not reached_paid
        and status is OrderStatus.IN_PROGRESS
    )


def can_cancel(
    *,
    status: OrderStatus,
    payment_method: PaymentMethod,
    reached_paid: bool,
    lines: Iterable[CustomerOrderLine],
) -> bool:
    """SRS 8.9 / ADR-024 d8, on the unmasked line states: a physical line, cash or a
    payment that reached paid, a cancellable status, every physical line `pending`."""
    physical = [
        line.fulfillment_status for line in lines if line.product_type is ProductType.PHYSICAL
    ]
    return (
        bool(physical)
        and (payment_method is PaymentMethod.CASH or reached_paid)
        and status in CANCELLABLE_ORDER_STATUSES
        and all(s is OrderItemStatus.PENDING for s in physical)
    )
