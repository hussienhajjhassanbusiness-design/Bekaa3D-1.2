"""Legal line edges (SRS 20.3-20.5), pure. VS-029 adds the physical forward edges; the
cancel and return edges are VS-031's (ADR-040 d1)."""

from dataclasses import dataclass
from enum import StrEnum

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import FulfillmentMethod, PaymentMethod
from app.ordering.domain.enums import OrderItemStatus as S


class TransitionRefusal(StrEnum):
    ALREADY_DELIVERED = "already_delivered"
    LINE_CLOSED = "line_closed"
    NOT_AWAITING_DELIVERY = "not_awaiting_delivery"
    PAYMENT_REQUIRED = "payment_required"
    CASH_HANDOVER_REQUIRED = "cash_handover_required"
    NOT_A_LEGAL_EDGE = "not_a_legal_edge"


@dataclass(frozen=True)
class LineContext:
    """What decides a line's edges: its type, the order's two methods and BR-148's gate."""

    product_type: ProductType
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_reached_paid: bool


Edges = dict[S, tuple[S, ...]]
STL_EDGES: Edges = {S.AWAITING_DELIVERY: (S.DELIVERED,)}
DELIVERY_EDGES: Edges = {
    S.PENDING: (S.IN_PRODUCTION,),
    S.IN_PRODUCTION: (S.READY_TO_SHIP,),
    S.READY_TO_SHIP: (S.SHIPPED,),
    S.SHIPPED: (S.DELIVERED,),
}
PICKUP_EDGES: Edges = {
    S.PENDING: (S.IN_PRODUCTION,),
    S.IN_PRODUCTION: (S.READY_FOR_PICKUP,),
    S.READY_FOR_PICKUP: (S.PICKED_UP,),
}
HANDOVER_TARGETS = frozenset({S.DELIVERED, S.PICKED_UP})
CLOSED = frozenset({S.REFUNDED, S.CANCELLED})


def _edges(ctx: LineContext) -> Edges:
    if ctx.product_type is ProductType.STL:
        return STL_EDGES
    if ctx.fulfillment_method is FulfillmentMethod.DELIVERY:
        return DELIVERY_EDGES
    if ctx.fulfillment_method is FulfillmentMethod.PICKUP:
        return PICKUP_EDGES
    return {}


def line_transition_refusal(ctx: LineContext, current: S, target: S) -> TransitionRefusal | None:
    """None when the endpoint accepts the edge; else the stable `reason` of the 409."""
    legal = target in _edges(ctx).get(current, ())
    if ctx.product_type is ProductType.STL:
        if legal:
            return None
        if target is not S.DELIVERED:
            return TransitionRefusal.NOT_A_LEGAL_EDGE
        if current is S.DELIVERED:
            return TransitionRefusal.ALREADY_DELIVERED
        if current in CLOSED:
            return TransitionRefusal.LINE_CLOSED
        return TransitionRefusal.NOT_AWAITING_DELIVERY
    if ctx.payment_method is not PaymentMethod.CASH and not ctx.payment_reached_paid:
        return TransitionRefusal.PAYMENT_REQUIRED
    if not legal:
        return (
            TransitionRefusal.LINE_CLOSED
            if current in CLOSED
            else TransitionRefusal.NOT_A_LEGAL_EDGE
        )
    if ctx.payment_method is PaymentMethod.CASH and target in HANDOVER_TARGETS:
        return TransitionRefusal.CASH_HANDOVER_REQUIRED
    return None


def available_targets(ctx: LineContext, current: S) -> tuple[S, ...]:
    """ADR-025 `available_actions`: exactly the targets the refusal above accepts."""
    return tuple(
        t for t in _edges(ctx).get(current, ()) if line_transition_refusal(ctx, current, t) is None
    )
