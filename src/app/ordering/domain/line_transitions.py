"""Legal line edges (SRS 20.1), pure. VS-029 adds the physical edges to `LEGAL_EDGES`."""

from enum import StrEnum

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus as S


class TransitionRefusal(StrEnum):
    ALREADY_DELIVERED = "already_delivered"
    LINE_CLOSED = "line_closed"
    NOT_AWAITING_DELIVERY = "not_awaiting_delivery"
    NOT_AN_STL_LINE = "not_an_stl_line"


LEGAL_EDGES: dict[tuple[ProductType, S], tuple[S, ...]] = {
    (ProductType.STL, S.AWAITING_DELIVERY): (S.DELIVERED,),
}


def line_transition_refusal(
    product_type: ProductType, current: S, target: S
) -> TransitionRefusal | None:
    """None when the edge is legal; else the stable `reason` of the 409."""
    if target in LEGAL_EDGES.get((product_type, current), ()):
        return None
    if product_type is not ProductType.STL:
        return TransitionRefusal.NOT_AN_STL_LINE
    if current is S.DELIVERED:
        return TransitionRefusal.ALREADY_DELIVERED
    if current in (S.REFUNDED, S.CANCELLED):
        return TransitionRefusal.LINE_CLOSED
    return TransitionRefusal.NOT_AWAITING_DELIVERY
