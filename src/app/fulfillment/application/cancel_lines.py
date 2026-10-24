"""Cancellation (VS-031; FR-09, BR-144, ADR-043): the customer's, the administrator's whole
order, and one line through the transition endpoint. One transaction, the caller's, in the
ADR-024 d9 order: order and lines, payments and the refund, the lines, any block, status."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.fulfillment.application.ports import FulfillmentNotices, FulfillmentOrders, OrderPayments
from app.ordering.public import (
    CancelReason,
    LineCancel,
    LineNotFoundError,
    LineState,
    LockedOrder,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
    admin_cancels,
    amount_due_cents,
    cash_block_reason,
    customer_cancels,
    line_cancel,
    line_context,
    order_facts,
    step_newly_reached,
)
from app.payments.public import CancellationRefund
from app.platform.application.ports import AuditWriter

S = OrderItemStatus


@dataclass(frozen=True)
class CancelDeps:
    orders: FulfillmentOrders
    payments: OrderPayments
    audit: AuditWriter
    notices: FulfillmentNotices


@dataclass(frozen=True)
class CancelContext:
    actor_user_id: UUID
    at: datetime
    note: str | None
    request_id: str | None
    ip_hash: str | None


@dataclass(frozen=True)
class CancelOutcome:
    order_status: OrderStatus
    refund_id: UUID | None
    blocked: bool


async def cancel_by_customer(
    deps: CancelDeps, *, order_id: UUID, ctx: CancelContext
) -> CancelOutcome:
    """FR-09: another customer's order is the same LineNotFoundError (404) as no order."""
    locked = await deps.orders.lock(order_id)
    if locked is None or locked.order.user_id != ctx.actor_user_id:
        raise LineNotFoundError(f"order {order_id} is not this customer's")
    paid = await deps.payments.reached_paid(order_id)
    cancels = customer_cancels(order_facts(locked, reached_paid=paid), locked.lines)
    return await _cancel(deps, locked, cancels, paid, ctx, by_customer=True)


async def cancel_by_admin(
    deps: CancelDeps, *, order_id: UUID, cancel_reason: CancelReason | None, ctx: CancelContext
) -> CancelOutcome:
    locked = await _lock(deps, order_id)
    paid = await deps.payments.reached_paid(order_id)
    cancels = admin_cancels(order_facts(locked, reached_paid=paid), locked.lines, cancel_reason)
    return await _cancel(deps, locked, cancels, paid, ctx, by_customer=False)


async def cancel_line_by_admin(
    deps: CancelDeps,
    *,
    order_id: UUID,
    item_id: UUID,
    cancel_reason: CancelReason | None,
    ctx: CancelContext,
) -> CancelOutcome:
    """The transition endpoint's `-> cancelled`, on the same table as `available_actions`."""
    locked = await _lock(deps, order_id)
    line = next((item for item in locked.lines if item.id == item_id), None)
    if line is None:
        raise LineNotFoundError(f"line {item_id} is not on order {order_id}")
    paid = await deps.payments.reached_paid(order_id)
    cancel = line_cancel(line_context(locked, line, reached_paid=paid), line, cancel_reason)
    return await _cancel(deps, locked, (cancel,), paid, ctx, by_customer=False)


async def _lock(deps: CancelDeps, order_id: UUID) -> LockedOrder:
    locked = await deps.orders.lock(order_id)
    if locked is None:
        raise LineNotFoundError(f"order {order_id} does not exist")
    return locked


async def _cancel(
    deps: CancelDeps,
    locked: LockedOrder,
    cancels: tuple[LineCancel, ...],
    paid: bool,
    ctx: CancelContext,
    *,
    by_customer: bool,
) -> CancelOutcome:
    order = locked.order
    refund = None
    if paid:  # an unpaid cash line was never paid: nothing to refund (BR-149)
        refund = await deps.payments.cancellation_refund(
            locked,
            frozenset(c.line_id for c in cancels),
            actor_user_id=ctx.actor_user_id,
            by_customer=by_customer,
            at=ctx.at,
            request_id=ctx.request_id,
            ip_hash=ctx.ip_hash,
        )
    await deps.orders.cancel(
        locked,
        cancels,
        actor_user_id=ctx.actor_user_id,
        at=ctx.at,
        note=ctx.note,
        by_customer=by_customer,
    )
    reasons = {c.line_id: c.cancel_reason for c in cancels}
    after = [
        (S.CANCELLED, reasons[line.id])
        if line.id in reasons
        else (line.fulfillment_status, line.cancel_reason)
        for line in locked.lines
    ]
    block = None if paid else cash_block_reason(order.payment_method, after)
    blocked = block is not None and await deps.orders.insert_cash_block(
        locked, reason=block, at=ctx.at
    )
    status = await deps.orders.recompute(
        locked,
        tuple(LineState(state) for state, _ in after),
        reached_paid=paid,
        refunds=await deps.payments.refund_facts(order.id),
        actor_user_id=ctx.actor_user_id,
    )
    await _audit(deps, locked, cancels, status, refund, blocked, ctx, by_customer)
    await _notify(deps, locked, cancels, after, paid, status, refund)
    return CancelOutcome(status, refund.refund_id if refund else None, blocked)


async def _audit(
    deps: CancelDeps,
    locked: LockedOrder,
    cancels: tuple[LineCancel, ...],
    status: OrderStatus,
    refund: CancellationRefund | None,
    blocked: bool,
    ctx: CancelContext,
    by_customer: bool,
) -> None:
    """One `order.cancelled` row per request (Q10): ids, states and reasons, no phone."""
    await deps.audit.record(
        actor_user_id=ctx.actor_user_id,
        action="order.cancelled",
        entity_type="order",
        entity_id=locked.order.id,
        before_data={"status": locked.order.status.value},
        after_data={
            "status": status.value,
            "order_number": locked.order.order_number,
            "by": "customer" if by_customer else "administrator",
            "lines": [
                {
                    "order_item_id": str(c.line_id),
                    "from_status": c.from_status.value,
                    "cancel_reason": c.cancel_reason.value if c.cancel_reason else None,
                }
                for c in cancels
            ],
            "refund_id": str(refund.refund_id) if refund else None,
            "refund_cents": refund.amount_cents if refund else None,
            "cash_block": blocked,
            "note": ctx.note,
        },
        request_id=ctx.request_id,
        ip_hash=ctx.ip_hash,
    )


async def _notify(
    deps: CancelDeps,
    locked: LockedOrder,
    cancels: tuple[LineCancel, ...],
    after: list[tuple[OrderItemStatus, CancelReason | None]],
    paid: bool,
    status: OrderStatus,
    refund: CancellationRefund | None,
) -> None:
    """The cancel notice, with the new amount due on a cash order still live (VS-031), then
    any step the cancel newly reached for the lines left (ADR-040 d2)."""
    ids = {c.line_id for c in cancels}
    order = locked.order
    live = [
        line
        for line, (state, _) in zip(locked.lines, after, strict=True)
        if state is not S.CANCELLED
    ]
    cash_due = order.payment_method is PaymentMethod.CASH and not paid and bool(live)
    await deps.notices.order_cancelled(
        locked,
        tuple(line for line in locked.lines if line.id in ids),
        order_cancelled=status is OrderStatus.CANCELLED,
        amount_due_cents=amount_due_cents(live) if cash_due else None,
        refund_cents=refund.amount_cents if refund else None,
    )
    physical = [
        (line.fulfillment_status, state)
        for line, (state, _) in zip(locked.lines, after, strict=True)
        if line.product_type is ProductType.PHYSICAL
    ]
    step = step_newly_reached(
        order.fulfillment_method, [b for b, _ in physical], [a for _, a in physical]
    )
    if step is not None:
        await deps.notices.step_reached(locked, step)
