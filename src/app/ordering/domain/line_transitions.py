"""Legal line edges (SRS 20.3-20.5), pure. VS-029 added the physical forward edges; VS-031
the cancel and return edges, with the cancel reasons each state takes (ADR-040 d1)."""

from dataclasses import dataclass
from enum import StrEnum

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import CancelReason, FulfillmentMethod, PaymentMethod
from app.ordering.domain.enums import OrderItemStatus as S


class TransitionRefusal(StrEnum):
    ALREADY_DELIVERED = "already_delivered"
    LINE_CLOSED = "line_closed"
    NOT_AWAITING_DELIVERY = "not_awaiting_delivery"
    PAYMENT_REQUIRED = "payment_required"
    CASH_HANDOVER_REQUIRED = "cash_handover_required"
    NOT_A_LEGAL_EDGE = "not_a_legal_edge"
    CANCEL_REASON_REQUIRED = "cancel_reason_required"
    CANCEL_REASON_NOT_ALLOWED = "cancel_reason_not_allowed"
    NO_CANCELLABLE_LINE = "no_cancellable_line"  # the admin order cancel only


@dataclass(frozen=True)
class LineContext:
    """What decides a line's edges: its type and total, the order's two methods and
    BR-148's gate."""

    product_type: ProductType
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_reached_paid: bool
    line_total_cents: int


Edges = dict[S, tuple[S, ...]]
STL_EDGES: Edges = {S.AWAITING_DELIVERY: (S.DELIVERED,)}
DELIVERY_EDGES: Edges = {
    S.PENDING: (S.IN_PRODUCTION, S.CANCELLED),
    S.IN_PRODUCTION: (S.READY_TO_SHIP, S.CANCELLED),
    S.READY_TO_SHIP: (S.SHIPPED, S.CANCELLED),
    S.SHIPPED: (S.DELIVERED, S.RETURNED, S.CANCELLED),
    S.RETURNED: (S.SHIPPED, S.IN_PRODUCTION, S.CANCELLED),
}
PICKUP_EDGES: Edges = {
    S.PENDING: (S.IN_PRODUCTION, S.CANCELLED),
    S.IN_PRODUCTION: (S.READY_FOR_PICKUP, S.CANCELLED),
    S.READY_FOR_PICKUP: (S.PICKED_UP, S.CANCELLED),
}
HANDOVER_TARGETS = frozenset({S.DELIVERED, S.PICKED_UP})
CLOSED = frozenset({S.REFUNDED, S.CANCELLED})
_REFUSED, _NO_SHOW, _OTHER = CancelReason.REFUSED, CancelReason.NO_SHOW, CancelReason.OTHER
# The reasons a cancel from each state takes; empty: it takes none (BR-144, 3.4b).
CANCEL_REASONS: dict[S, tuple[CancelReason, ...]] = {
    S.PENDING: (),
    S.IN_PRODUCTION: (),
    S.READY_TO_SHIP: (_REFUSED, _OTHER),
    S.READY_FOR_PICKUP: (_REFUSED, _NO_SHOW, _OTHER),
    S.RETURNED: (_REFUSED, _OTHER),
    S.SHIPPED: (_OTHER,),
}


def _edges(ctx: LineContext) -> Edges:
    if ctx.product_type is ProductType.STL:
        return STL_EDGES
    if ctx.fulfillment_method is FulfillmentMethod.DELIVERY:
        return DELIVERY_EDGES
    if ctx.fulfillment_method is FulfillmentMethod.PICKUP:
        return PICKUP_EDGES
    return {}


def _unpaid_cash(ctx: LineContext) -> bool:
    return ctx.payment_method is PaymentMethod.CASH and not ctx.payment_reached_paid


def _legal(ctx: LineContext, current: S, target: S) -> bool:
    """A paid `shipped` or `returned` line comes back and is refunded instead (SRS 20.4)."""
    if target not in _edges(ctx).get(current, ()):
        return False
    if target is S.CANCELLED and current is S.SHIPPED:
        return _unpaid_cash(ctx) and ctx.line_total_cents == 0
    if target is S.CANCELLED and current is S.RETURNED:
        return _unpaid_cash(ctx)
    return True


def line_transition_refusal(
    ctx: LineContext, current: S, target: S, cancel_reason: CancelReason | None = None
) -> TransitionRefusal | None:
    """None when the endpoint accepts the edge; else the stable `reason` of the 409."""
    legal = _legal(ctx, current, target)
    if ctx.product_type is ProductType.STL:
        if legal and cancel_reason is None:
            return None
        if target is not S.DELIVERED or cancel_reason is not None:
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
    return _reason_refusal(current, target, cancel_reason)


def _reason_refusal(
    current: S, target: S, cancel_reason: CancelReason | None
) -> TransitionRefusal | None:
    reasons = CANCEL_REASONS.get(current, ()) if target is S.CANCELLED else ()
    if cancel_reason is None:
        return TransitionRefusal.CANCEL_REASON_REQUIRED if reasons else None
    return None if cancel_reason in reasons else TransitionRefusal.CANCEL_REASON_NOT_ALLOWED


def available_actions(
    ctx: LineContext, current: S
) -> tuple[tuple[S, tuple[CancelReason, ...]], ...]:
    """ADR-025 `available_actions`: each target the refusal above accepts, with the reasons
    it takes (empty: none, otherwise one is required)."""
    out = []
    for target in _edges(ctx).get(current, ()):
        reasons = CANCEL_REASONS.get(current, ()) if target is S.CANCELLED else ()
        if line_transition_refusal(ctx, current, target, reasons[0] if reasons else None) is None:
            out.append((target, reasons))
    return tuple(out)


def available_targets(ctx: LineContext, current: S) -> tuple[S, ...]:
    return tuple(target for target, _ in available_actions(ctx, current))
