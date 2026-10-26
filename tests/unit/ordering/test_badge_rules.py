"""VS-036 plan 3.1 and 6.1: every line state x product type, against the badge table."""

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.badge import line_earns_badge
from app.ordering.domain.enums import OrderItemStatus as S

EARNING = {
    (ProductType.STL, S.AWAITING_DELIVERY),
    (ProductType.STL, S.DELIVERED),
    (ProductType.PHYSICAL, S.DELIVERED),
    (ProductType.PHYSICAL, S.PICKED_UP),
}


@pytest.mark.parametrize("product_type", list(ProductType))
@pytest.mark.parametrize("status", list(S))
def test_only_owned_stl_and_received_physical_lines_earn(
    product_type: ProductType, status: S
) -> None:
    assert line_earns_badge(product_type, status) is ((product_type, status) in EARNING)


@pytest.mark.parametrize(
    "status", [S.RETURNED, S.CANCELLED, S.REFUNDED, S.SHIPPED, S.READY_FOR_PICKUP, S.PENDING]
)
def test_returned_cancelled_refunded_and_unreceived_never_earn(status: S) -> None:
    assert not line_earns_badge(ProductType.PHYSICAL, status)
    assert not line_earns_badge(ProductType.STL, status)
