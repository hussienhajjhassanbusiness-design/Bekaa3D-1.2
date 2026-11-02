"""The per-customer cap on unpaid `manual` orders (VS-050 audit Q-1, ADR-049 d14)."""

import pytest

from app.ordering.domain.exceptions import ManualOrderLimitReachedError
from app.ordering.domain.manual_orders import manual_order_limit


@pytest.mark.parametrize(("open_orders", "max_open"), [(0, 1), (2, 3), (9, 10)])
def test_an_order_below_the_cap_is_allowed(open_orders: int, max_open: int) -> None:
    manual_order_limit(open_orders=open_orders, max_open=max_open)


@pytest.mark.parametrize(("open_orders", "max_open"), [(1, 1), (3, 3), (4, 3)])
def test_an_order_at_or_over_the_cap_is_refused(open_orders: int, max_open: int) -> None:
    with pytest.raises(ManualOrderLimitReachedError) as refused:
        manual_order_limit(open_orders=open_orders, max_open=max_open)
    assert refused.value.max_open_orders == max_open
