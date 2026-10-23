"""The cash handover rule (SRS 9.8.3, BR-143), pure: the lines it needs and what it is owed."""

from collections.abc import Sequence
from enum import StrEnum

from app.ordering.domain.enums import FulfillmentMethod, PaymentMethod
from app.ordering.domain.enums import OrderItemStatus as S

READY = {FulfillmentMethod.DELIVERY: S.SHIPPED, FulfillmentMethod.PICKUP: S.READY_FOR_PICKUP}
HANDED_OVER = {FulfillmentMethod.DELIVERY: S.DELIVERED, FulfillmentMethod.PICKUP: S.PICKED_UP}
_AFTER_HANDOVER = frozenset({S.DELIVERED, S.PICKED_UP, S.REFUNDED})


class HandoverRefusal(StrEnum):
    NOT_A_CASH_ORDER = "not_a_cash_order"
    NO_LIVE_LINE = "no_live_line"
    ALREADY_RECORDED = "already_recorded"
    LINES_NOT_READY = "lines_not_ready"


def handover_refusal(
    payment_method: PaymentMethod, method: FulfillmentMethod | None, states: Sequence[S]
) -> HandoverRefusal | None:
    """The 409 reasons, in this order; `states` are every line's, cancelled ones included."""
    if payment_method is not PaymentMethod.CASH or method is None:
        return HandoverRefusal.NOT_A_CASH_ORDER
    live = [s for s in states if s is not S.CANCELLED]
    if not live:
        return HandoverRefusal.NO_LIVE_LINE
    if any(s in _AFTER_HANDOVER for s in live):
        return HandoverRefusal.ALREADY_RECORDED
    if any(s is not READY[method] for s in live):
        return HandoverRefusal.LINES_NOT_READY
    return None


def handover_amount_matches(*, due_cents: int, typed_cents: int) -> bool:
    """BR-055 / BR-143: exactly the live total, and above zero."""
    return due_cents > 0 and typed_cents == due_cents
