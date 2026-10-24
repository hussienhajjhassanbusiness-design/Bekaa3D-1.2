"""`POST …/items/{item_id}/transition` (VS-029): one line, one edge, one transaction (the
caller's): lock, decide on the locked state, history, status, audit, any order notice.
`-> cancelled` is VS-031's cancel, so it refunds and may block cash like the others."""

from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.fulfillment.application.cancel_lines import (
    CancelContext,
    CancelDeps,
    cancel_line_by_admin,
)
from app.fulfillment.application.mark_stl_delivered import deliver_stl_line
from app.fulfillment.application.ports import FulfillmentNotices, FulfillmentOrders, OrderPayments
from app.ordering.public import (
    CancelReason,
    InvalidLineTransitionError,
    LineNotFoundError,
    OrderItemStatus,
    OrderStatus,
    TransitionRefusal,
    step_reached,
)
from app.platform.application.ports import AuditWriter


async def transition_line(
    orders: FulfillmentOrders,
    payments: OrderPayments,
    audit: AuditWriter,
    notices: FulfillmentNotices,
    *,
    order_id: UUID,
    item_id: UUID,
    target: OrderItemStatus,
    admin_id: UUID,
    at: datetime,
    note: str | None,
    request_id: str | None,
    ip_hash: str | None,
    cancel_reason: CancelReason | None = None,
) -> OrderStatus:
    if target is OrderItemStatus.CANCELLED:
        outcome = await cancel_line_by_admin(
            CancelDeps(orders, payments, audit, notices),
            order_id=order_id,
            item_id=item_id,
            cancel_reason=cancel_reason,
            ctx=CancelContext(admin_id, at, note, request_id, ip_hash),
        )
        return outcome.order_status
    if cancel_reason is not None:
        raise InvalidLineTransitionError(TransitionRefusal.CANCEL_REASON_NOT_ALLOWED.value)
    locked = await orders.lock(order_id)
    if locked is None:
        raise LineNotFoundError(f"order {order_id} does not exist")
    line = next((item for item in locked.lines if item.id == item_id), None)
    if line is None:
        raise LineNotFoundError(f"line {item_id} is not on order {order_id}")
    # Every payment and refund writer locks the order first, so neither changes under us.
    refunds = await payments.refund_facts(order_id)
    if line.product_type is ProductType.STL:
        if target is not OrderItemStatus.DELIVERED:
            raise InvalidLineTransitionError(
                TransitionRefusal.NOT_A_LEGAL_EDGE.value,
                current_status=line.fulfillment_status.value,
            )
        delivered = await deliver_stl_line(
            orders,
            audit,
            notices,
            locked,
            refunds=refunds,
            item_id=item_id,
            admin_id=admin_id,
            at=at,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return delivered.order_status
    # Every payment writer locks the order first, so this cannot change under us (ADR-024).
    reached_paid = await payments.reached_paid(order_id)
    _, order_status = await orders.transition(
        locked,
        line_id=item_id,
        target=target,
        admin_id=admin_id,
        at=at,
        reached_paid=reached_paid,
        refunds=refunds,
        note=note,
    )
    await audit.record(
        actor_user_id=admin_id,
        action="order_item.transitioned",
        entity_type="order_item",
        entity_id=item_id,
        before_data={"fulfillment_status": line.fulfillment_status.value},
        after_data={
            "fulfillment_status": target.value,
            "order_id": str(order_id),
            "order_number": locked.order.order_number,
            "order_status": order_status.value,
            "note": note,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    physical = [
        target if item.id == item_id else item.fulfillment_status
        for item in locked.lines
        if item.product_type is ProductType.PHYSICAL
    ]
    if step_reached(locked.order.fulfillment_method, target, physical):
        await notices.step_reached(locked, target)
    return order_status
