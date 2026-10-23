"""`record_cash_handover()` (VS-029; SRS 9.8.3, BR-143, glossary rule 6): the only creator
of a cash payment. One transaction, the caller's, in the ADR-024 handover lock order."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.fulfillment.application.ports import FulfillmentNotices, FulfillmentOrders, OrderPayments
from app.ordering.public import LineNotFoundError, OrderStatus, check_cash_handover
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class HandoverResult:
    order_id: UUID
    payment_id: UUID
    amount_cents: int
    order_status: OrderStatus


async def record_cash_handover(
    orders: FulfillmentOrders,
    payments: OrderPayments,
    audit: AuditWriter,
    notices: FulfillmentNotices,
    *,
    order_id: UUID,
    amount_cents: int,
    admin_id: UUID,
    at: datetime,
    note: str | None,
    request_id: str | None,
    ip_hash: str | None,
) -> HandoverResult:
    """Raises HandoverRefusedError (409), CashAmountMismatchError (422) or
    CashAlreadyRecordedError; the caller's rollback then leaves nothing written."""
    locked = await orders.lock(order_id)  # orders, then every line by id
    if locked is None:
        raise LineNotFoundError(f"order {order_id} does not exist")
    due = check_cash_handover(locked, typed_cents=amount_cents)
    payment_id = await payments.record_cash(
        order_id=order_id,
        amount_cents=due,
        currency=locked.order.currency,
        admin_id=admin_id,
        at=at,
    )
    lines, order_status = await orders.hand_over(locked, admin_id=admin_id, at=at, note=note)
    await audit.record(
        actor_user_id=admin_id,
        action="order.cash_handover",
        entity_type="order",
        entity_id=order_id,
        before_data={"status": locked.order.status.value},
        after_data={
            "status": order_status.value,
            "order_number": locked.order.order_number,
            "payment_id": str(payment_id),
            "amount_cents": due,
            "currency": locked.order.currency,
            "line_ids": [str(line.id) for line in lines],
            "fulfillment_status": lines[0].fulfillment_status.value,
            "note": note,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    await notices.cash_handed_over(locked, payment_id=payment_id, amount_cents=due, recorded_at=at)
    return HandoverResult(order_id, payment_id, due, order_status)
