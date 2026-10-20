"""What a customer may see of an order (VS-025; SRS 8.9, ADR-024 d8). Pure.
`in_production` ("start printing") is internal: shown as `pending`, absent from history."""

from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry
from app.ordering.domain.payment_recovery import hold_deadline, retry_refusal

HIDDEN_STATUS = OrderItemStatus.IN_PRODUCTION
CANCELLABLE_ORDER_STATUSES = frozenset({OrderStatus.IN_PROGRESS, OrderStatus.PARTIALLY_REFUNDED})
LIVE_ATTEMPT_STATUSES = frozenset({"pending", "processing"})


def customer_line_status(status: OrderItemStatus) -> OrderItemStatus:
    return OrderItemStatus.PENDING if status is HIDDEN_STATUS else status


def customer_lines(lines: Iterable[CustomerOrderLine]) -> list[CustomerOrderLine]:
    return [
        replace(line, fulfillment_status=customer_line_status(line.fulfillment_status))
        for line in lines
    ]


def customer_history(entries: Iterable[HistoryEntry]) -> list[HistoryEntry]:
    """Entries into `in_production` are dropped; the next one out of it reads as from the
    state before it (`pending`, or `returned` on a reprint). A no-op that leaves is dropped."""
    before_hidden: dict[UUID | None, str] = {}
    shown = []
    for entry in entries:
        if entry.to_status == HIDDEN_STATUS.value:
            before_hidden[entry.order_item_id] = entry.from_status or OrderItemStatus.PENDING
            continue
        if entry.from_status == HIDDEN_STATUS.value:
            earlier = before_hidden.pop(entry.order_item_id, OrderItemStatus.PENDING.value)
            entry = replace(entry, from_status=earlier)
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
    """SRS 8.9 as amended by the owner (ADR-033 d4), on unmasked states: a live (not
    cancelled) physical line, cash or paid, a cancellable status, every live one `pending`."""
    live_physical = [
        line.fulfillment_status
        for line in lines
        if line.product_type is ProductType.PHYSICAL
        and line.fulfillment_status is not OrderItemStatus.CANCELLED
    ]
    return (
        bool(live_physical)
        and (payment_method is PaymentMethod.CASH or reached_paid)
        and status in CANCELLABLE_ORDER_STATUSES
        and all(s is OrderItemStatus.PENDING for s in live_physical)
    )


def can_retry_payment(
    order: CustomerOrder,
    lines: Sequence[CustomerOrderLine],
    *,
    attempt_status: str | None,
    offer_open: bool,
    now: datetime,
    hold: timedelta,
) -> bool:
    """VS-024's T1 without the lock, and false while an attempt is live or an offer order's
    window has closed, both of which the retry refuses (ADR-037). The POST re-checks."""
    return (
        retry_refusal(order, lines, now=now, hold=hold) is None
        and attempt_status not in LIVE_ATTEMPT_STATUSES
        and offer_open
    )


def hold_expires_at(
    order: CustomerOrder, *, latest_initiated_at: datetime | None, hold: timedelta
) -> datetime | None:
    """When an unpaid online order may be released (VS-024 D4); None for any other order."""
    if (
        order.payment_method is not PaymentMethod.ONLINE
        or order.status is not OrderStatus.PENDING_PAYMENT
        or order.cancelled_at is not None
    ):
        return None
    return hold_deadline(order.placed_at, latest_initiated_at, hold)
