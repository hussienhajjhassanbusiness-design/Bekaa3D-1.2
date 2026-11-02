"""The per-customer cap on unpaid `manual` orders (VS-050 audit Q-1, ADR-049 d14). Pure."""

from typing import Final

from app.ordering.domain.exceptions import ManualOrderLimitReachedError

# int4 namespace of the two-int advisory lock taken per customer before the order INSERT.
MANUAL_ORDERS_LOCK_NS: Final = 0x4D414E55
MAX_OPEN_SETTING: Final = "manual_max_open_orders"


def manual_order_limit(*, open_orders: int, max_open: int) -> None:
    """Under the customer's lock: one more order must stay within the cap."""
    if open_orders >= max_open:
        raise ManualOrderLimitReachedError(max_open)
