"""Retry and hold-release rules for an unpaid online order (VS-024 plan 3.1, T1, 2.5). Pure:
timings arrive as parameters, so Ordering imports nothing from Payments here."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod


class PayableOrder(Protocol):
    """An `Order` or a `CustomerOrder`: what the retry and release rules read."""

    @property
    def payment_method(self) -> PaymentMethod: ...
    @property
    def status(self) -> OrderStatus: ...
    @property
    def placed_at(self) -> datetime: ...
    @property
    def cancelled_at(self) -> datetime | None: ...


class PayableLine(Protocol):
    @property
    def fulfillment_status(self) -> OrderItemStatus: ...


# The online provider whose attempts the administrator confirms by hand (ADR-049).
MANUAL_PROVIDER = "manual"


@dataclass(frozen=True)
class Holds:
    """`checkout_hold_period`, and `manual_payment_hold_period` for a `manual` attempt."""

    online: timedelta
    manual: timedelta

    def for_provider(self, provider: str | None) -> timedelta:
        return self.manual if provider == MANUAL_PROVIDER else self.online

    @property
    def shortest(self) -> timedelta:
        return min(self.online, self.manual)


class RetryRefusal(StrEnum):
    """409 INVALID_STATE_TRANSITION `reason` values, in T1's order."""

    CASH_ORDER = "cash_order"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_NOT_PAYABLE = "order_not_payable"
    CHECKOUT_HOLD_EXPIRED = "checkout_hold_expired"
    # VS-041: an offer order whose offer is no longer accepted or whose window closed.
    OFFER_CHECKOUT_EXPIRED = "offer_checkout_expired"


class ReleaseRefusal(StrEnum):
    """409 INVALID_STATE_TRANSITION `reason` values for the manual release (plan 2.5)."""

    CASH_ORDER = "cash_order"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_NOT_PAYABLE = "order_not_payable"
    GRACE_NOT_ELAPSED = "grace_not_elapsed"
    UNPROCESSED_EVENTS = "unprocessed_events"


def hold_deadline(
    placed_at: datetime, latest_initiated_at: datetime | None, hold: timedelta
) -> datetime:
    """D4: measured from the later of placement and the latest attempt."""
    start = placed_at if latest_initiated_at is None else max(placed_at, latest_initiated_at)
    return start + hold


def manual_release_available_at(
    deadline: datetime, grace: timedelta, *, early: bool, manual_from: datetime | None = None
) -> datetime:
    """`early` (Revision 2, Q7): no stored provider reference and a latest answer `unknown`.
    `manual_from`: a `manual` attempt's order may be released from placement (VS-050 Q3)."""
    if manual_from is not None:
        return manual_from
    return deadline if early else deadline + grace


def _unpayable(order: PayableOrder, lines: Sequence[PayableLine]) -> bool:
    return order.status is not OrderStatus.PENDING_PAYMENT or any(
        line.fulfillment_status is not OrderItemStatus.PENDING for line in lines
    )


def retry_refusal(
    order: PayableOrder, lines: Sequence[PayableLine], *, now: datetime, hold: timedelta
) -> RetryRefusal | None:
    """T1, first match wins; read under the orders lock. A live attempt is the index's job."""
    if order.payment_method is PaymentMethod.CASH:
        return RetryRefusal.CASH_ORDER
    if order.cancelled_at is not None:
        return RetryRefusal.ORDER_CANCELLED
    if _unpayable(order, lines):
        return RetryRefusal.ORDER_NOT_PAYABLE
    if now >= order.placed_at + hold:
        return RetryRefusal.CHECKOUT_HOLD_EXPIRED
    return None


def can_retry_payment(
    order: PayableOrder, lines: Sequence[PayableLine], *, now: datetime, hold: timedelta
) -> bool:
    """T1 without the lock, for VS-025's `OrderDetail`; the POST re-checks under the lock."""
    return retry_refusal(order, lines, now=now, hold=hold) is None


def manual_release_refusal(
    order: PayableOrder,
    lines: Sequence[PayableLine],
    *,
    now: datetime,
    available_at: datetime,
    unprocessed_events: int,
    events_reviewed: bool,
) -> ReleaseRefusal | None:
    """Plan 2.5 step 5, first match wins; read under orders, lines and payments locks."""
    if order.payment_method is PaymentMethod.CASH:
        return ReleaseRefusal.CASH_ORDER
    if order.cancelled_at is not None:
        return ReleaseRefusal.ORDER_CANCELLED
    if _unpayable(order, lines):
        return ReleaseRefusal.ORDER_NOT_PAYABLE
    if now < available_at:
        return ReleaseRefusal.GRACE_NOT_ELAPSED
    if unprocessed_events > 0 and not events_reviewed:
        return ReleaseRefusal.UNPROCESSED_EVENTS
    return None
