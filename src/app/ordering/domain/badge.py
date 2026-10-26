"""Which line states earn the Verified Purchase badge (VS-036 plan 3.1, ADR-044), pure.
A projection of current line facts: status alone, no Payments read (see the plan)."""

from typing import Final

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus as S

# STL: owned (ADR-019 d5). Physical: received; cash only reaches these after the handover.
BADGE_STATES: Final[dict[ProductType, frozenset[S]]] = {
    ProductType.STL: frozenset({S.AWAITING_DELIVERY, S.DELIVERED}),
    ProductType.PHYSICAL: frozenset({S.DELIVERED, S.PICKED_UP}),
}


def line_earns_badge(product_type: ProductType, status: S) -> bool:
    return status in BADGE_STATES[product_type]
