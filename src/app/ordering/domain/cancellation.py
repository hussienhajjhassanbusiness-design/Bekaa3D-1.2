"""Which lines a cancel takes, and the cash block rule (VS-031; FR-09, BR-144, SRS 20.4-20.5).
Pure: the caller passes the lines it read under the orders lock."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.customer_view import can_cancel
from app.ordering.domain.enums import (
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.exceptions import InvalidLineTransitionError, OrderNotCancellableError
from app.ordering.domain.line_transitions import (
    CANCEL_REASONS,
    LineContext,
    TransitionRefusal,
    line_transition_refusal,
)

S = OrderItemStatus
ADMIN_CANCELLABLE = frozenset({S.PENDING, S.IN_PRODUCTION, S.READY_TO_SHIP, S.READY_FOR_PICKUP})
BLOCKING_REASONS = frozenset({CancelReason.REFUSED, CancelReason.NO_SHOW})


class _Line(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def product_type(self) -> ProductType: ...

    @property
    def fulfillment_status(self) -> OrderItemStatus: ...

    @property
    def line_total_cents(self) -> int: ...


@dataclass(frozen=True)
class LineCancel:
    line_id: UUID
    from_status: OrderItemStatus
    cancel_reason: CancelReason | None


@dataclass(frozen=True)
class OrderFacts:
    status: OrderStatus
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_reached_paid: bool


def line_context(order: OrderFacts, line: _Line) -> LineContext:
    return LineContext(
        line.product_type,
        order.fulfillment_method,
        order.payment_method,
        order.payment_reached_paid,
        line.line_total_cents,
    )


def customer_cancels(order: OrderFacts, lines: Sequence[_Line]) -> tuple[LineCancel, ...]:
    """FR-09 under the locks, through the same `can_cancel` as the flag (ADR-033 d4): every
    live physical line, all `pending`; nothing changes when it refuses."""
    if not can_cancel(
        status=order.status,
        payment_method=order.payment_method,
        reached_paid=order.payment_reached_paid,
        lines=lines,
    ):
        raise OrderNotCancellableError("This order can no longer be cancelled.")
    return tuple(
        LineCancel(line.id, line.fulfillment_status, None)
        for line in lines
        if line.product_type is ProductType.PHYSICAL and line.fulfillment_status is S.PENDING
    )


def admin_cancels(
    order: OrderFacts,
    lines: Sequence[_Line],
    cancel_reason: CancelReason | None,
) -> tuple[LineCancel, ...]:
    """Every physical line still before shipping or collection. One reason for the request,
    recorded on the lines that take one; any refusal refuses the whole cancel."""
    eligible = [
        line
        for line in lines
        if line.product_type is ProductType.PHYSICAL
        and line.fulfillment_status in ADMIN_CANCELLABLE
    ]
    if order.payment_method is PaymentMethod.ONLINE and not order.payment_reached_paid:
        raise InvalidLineTransitionError(TransitionRefusal.PAYMENT_REQUIRED.value)
    if not eligible:
        raise InvalidLineTransitionError(TransitionRefusal.NO_CANCELLABLE_LINE.value)
    if cancel_reason is not None and not any(
        CANCEL_REASONS[x.fulfillment_status] for x in eligible
    ):
        raise InvalidLineTransitionError(TransitionRefusal.CANCEL_REASON_NOT_ALLOWED.value)
    out = []
    for line in eligible:
        current = line.fulfillment_status
        reason = cancel_reason if CANCEL_REASONS[current] else None
        line_cancel(line_context(order, line), line, reason)
        out.append(LineCancel(line.id, current, reason))
    return tuple(out)


def line_cancel(ctx: LineContext, line: _Line, reason: CancelReason | None) -> LineCancel:
    """One line, as the transition endpoint's `-> cancelled`; raises its 409 reason."""
    current = line.fulfillment_status
    refusal = line_transition_refusal(ctx, current, S.CANCELLED, reason)
    if refusal is not None:
        raise InvalidLineTransitionError(refusal.value, current_status=current.value)
    return LineCancel(line.id, current, reason)


def cash_block_reason(
    payment_method: PaymentMethod,
    lines_after: Iterable[tuple[OrderItemStatus, CancelReason | None]],
) -> CancelReason | None:
    """BR-144 over every line after the cancel, so cancel order cannot matter: a cash order
    with no live line whose reasons are all `refused`/`no_show` (at least one) blocks."""
    if payment_method is not PaymentMethod.CASH:
        return None
    after = list(lines_after)
    if not after or any(status is not S.CANCELLED for status, _ in after):
        return None
    reasons = {reason for _, reason in after if reason is not None}
    if not reasons or not reasons <= BLOCKING_REASONS:
        return None
    return CancelReason.REFUSED if CancelReason.REFUSED in reasons else CancelReason.NO_SHOW
