"""Which lines a receipt confirmation or problem report covers (VS-029b; ADR-041 d1)."""

import uuid

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.exceptions import NoDeliveredLineError
from app.ordering.domain.orders import OrderLine
from app.ordering.domain.receipt import RECEIVED_STATES, received_line_ids

PHYSICAL_STATES = [s for s in S if s is not S.AWAITING_DELIVERY]


def _line(kind: ProductType, status: S) -> OrderLine:
    return OrderLine(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        product_type=kind,
        product_name_snapshot="Lamp",
        unit_price_cents=1000,
        quantity=1,
        line_total_cents=1000,
        currency="USD",
        fulfillment_status=status,
    )


def test_only_delivered_and_picked_up_count_as_received() -> None:
    assert {S.DELIVERED, S.PICKED_UP} == RECEIVED_STATES


@pytest.mark.parametrize("status", sorted(RECEIVED_STATES))
def test_a_received_physical_line_is_covered(status: S) -> None:
    line = _line(ProductType.PHYSICAL, status)
    assert received_line_ids([line]) == [line.id]


@pytest.mark.parametrize("status", [s for s in PHYSICAL_STATES if s not in RECEIVED_STATES])
def test_a_physical_line_not_received_refuses_both_actions(status: S) -> None:
    with pytest.raises(NoDeliveredLineError) as raised:
        received_line_ids([_line(ProductType.PHYSICAL, status)])
    assert raised.value.reason == "no_delivered_line"


def test_a_delivered_stl_line_is_never_covered() -> None:
    with pytest.raises(NoDeliveredLineError):
        received_line_ids([_line(ProductType.STL, S.DELIVERED)])


def test_no_line_at_all_refuses() -> None:
    with pytest.raises(NoDeliveredLineError):
        received_line_ids([])


def test_a_mixed_order_covers_its_received_physical_lines_by_id() -> None:
    lines = [
        _line(ProductType.PHYSICAL, S.DELIVERED),
        _line(ProductType.STL, S.DELIVERED),
        _line(ProductType.PHYSICAL, S.SHIPPED),
        _line(ProductType.PHYSICAL, S.DELIVERED),
        _line(ProductType.PHYSICAL, S.CANCELLED),
    ]
    assert received_line_ids(lines) == sorted([lines[0].id, lines[3].id])
