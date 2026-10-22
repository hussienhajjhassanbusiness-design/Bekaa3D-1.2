"""Cash rules (VS-028 plan 3.1; SRS 9.8.1, BR-141, BR-145). Pure: counts arrive as arguments."""

from collections.abc import Iterable, Sequence
from typing import Final, Protocol

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus
from app.ordering.domain.exceptions import (
    CashLimitReachedError,
    CashNotAvailableError,
    PaymentMethodNotAllowedError,
)
from app.ordering.domain.orders import NewOrderLine

# int4 namespace of the two-int advisory lock; the one-bigint locks are another key space.
CASH_PHONE_LOCK_NS: Final = 0x43415348


class _Priced(Protocol):
    @property
    def line_total_cents(self) -> int: ...

    @property
    def fulfillment_status(self) -> OrderItemStatus: ...


def cash_precheck(
    lines: Sequence[NewOrderLine], total_cents: int, *, enabled: bool, max_total: int
) -> None:
    """Before the phone lock, so no phone-free refusal can follow a phone-matched one: all
    physical, enabled, a total above zero and within the cap (ADR-038)."""
    if any(line.product_type is not ProductType.PHYSICAL for line in lines):
        raise PaymentMethodNotAllowedError("cash_requires_physical")
    if not enabled:
        raise PaymentMethodNotAllowedError("cash_disabled")
    if total_cents <= 0:
        raise PaymentMethodNotAllowedError("zero_total")
    if total_cents > max_total:
        raise CashLimitReachedError("order_total")


def cash_limits(*, blocked: bool, open_orders: int, max_open: int) -> None:
    """Under the phone lock: one refusal for a block and for the open-order limit."""
    if blocked or open_orders >= max_open:
        raise CashNotAvailableError("Cash on delivery is not available for this order.")


def amount_due_cents(lines: Iterable[_Priced]) -> int:
    """The live total: every line that is not cancelled (ADR-033)."""
    return sum(
        line.line_total_cents
        for line in lines
        if line.fulfillment_status is not OrderItemStatus.CANCELLED
    )
