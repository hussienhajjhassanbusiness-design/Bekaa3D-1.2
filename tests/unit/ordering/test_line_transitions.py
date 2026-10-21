"""The STL line edge table (VS-023b): only awaiting_delivery -> delivered is legal."""

import itertools

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.line_transitions import TransitionRefusal, line_transition_refusal


def test_awaiting_delivery_to_delivered_is_the_only_legal_edge() -> None:
    legal = [
        (kind, cur, tgt)
        for kind, cur, tgt in itertools.product(ProductType, S, S)
        if line_transition_refusal(kind, cur, tgt) is None
    ]
    assert legal == [(ProductType.STL, S.AWAITING_DELIVERY, S.DELIVERED)]


@pytest.mark.parametrize(
    ("kind", "current", "reason"),
    [
        (ProductType.STL, S.DELIVERED, TransitionRefusal.ALREADY_DELIVERED),
        (ProductType.STL, S.REFUNDED, TransitionRefusal.LINE_CLOSED),
        (ProductType.STL, S.CANCELLED, TransitionRefusal.LINE_CLOSED),
        (ProductType.STL, S.PENDING, TransitionRefusal.NOT_AWAITING_DELIVERY),
        (ProductType.PHYSICAL, S.PENDING, TransitionRefusal.NOT_AN_STL_LINE),
        (ProductType.PHYSICAL, S.SHIPPED, TransitionRefusal.NOT_AN_STL_LINE),
        (ProductType.PHYSICAL, S.DELIVERED, TransitionRefusal.NOT_AN_STL_LINE),
    ],
)
def test_every_refusal_has_its_stable_reason(
    kind: ProductType, current: S, reason: TransitionRefusal
) -> None:
    assert line_transition_refusal(kind, current, S.DELIVERED) is reason
