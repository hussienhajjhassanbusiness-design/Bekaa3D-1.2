"""Receipt confirmation and problem reports (VS-029b; FR-21, BR-147, ADR-041). Neither
changes a line's state or the order status; both lock `orders`, then lines (ADR-024)."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.ordering.application.ports import ProblemReportInbox, ReceiptOrders
from app.ordering.domain.exceptions import ReceiptOrderNotFoundError
from app.ordering.domain.orders import Order
from app.ordering.domain.receipt import received_line_ids
from app.platform.application.ports import AuditWriter

ENTITY_TYPE = "order"


async def confirm_receipt(
    orders: ReceiptOrders,
    audit: AuditWriter,
    *,
    user_id: UUID,
    order_id: UUID,
    clock: Callable[[], datetime],
    request_id: str | None,
    ip_hash: str | None,
) -> list[UUID]:
    """Idempotent: a repeat stamps nothing and writes no audit row. Returns the ids set.
    The clock is read once the locks are held, as offer checkout does (ADR-037)."""
    order, line_ids = await _received(orders, user_id, order_id)
    stamped = await orders.stamp_receipt_confirmed(order_id, line_ids, at=clock())
    if stamped:
        await audit.record(
            actor_user_id=user_id,
            action="order.receipt_confirmed",
            entity_type=ENTITY_TYPE,
            entity_id=order_id,
            after_data={"order_number": order.order_number, "line_ids": _strs(stamped)},
            request_id=request_id,
            ip_hash=ip_hash,
        )
    return stamped


async def report_problem(
    orders: ReceiptOrders,
    inbox: ProblemReportInbox,
    audit: AuditWriter,
    *,
    user_id: UUID,
    email: str,
    order_id: UUID,
    message: str,
    clock: Callable[[], datetime],
    request_id: str | None,
    ip_hash: str | None,
) -> UUID:
    """Every report is a new contact message; the line timestamp keeps the first one.
    The audit row names the message, never its body (ADR-041 d2)."""
    order, line_ids = await _received(orders, user_id, order_id)
    message_id = await inbox.submit(
        user_id=user_id,
        order_id=order_id,
        order_number=order.order_number,
        recipient_name=order.recipient_name,
        email=email,
        message=message,
    )
    stamped = await orders.stamp_problem_reported(order_id, line_ids, at=clock())
    await audit.record(
        actor_user_id=user_id,
        action="order.problem_reported",
        entity_type=ENTITY_TYPE,
        entity_id=order_id,
        after_data={
            "order_number": order.order_number,
            "line_ids": _strs(stamped),
            "contact_message_id": str(message_id),
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return message_id


async def _received(
    orders: ReceiptOrders, user_id: UUID, order_id: UUID
) -> tuple[Order, list[UUID]]:
    order = await orders.lock_owned_order(order_id, user_id)
    if order is None:
        raise ReceiptOrderNotFoundError(f"order {order_id} is not the caller's")
    return order, received_line_ids(await orders.lock_lines(order_id))


def _strs(ids: list[UUID]) -> list[str]:
    return [str(line_id) for line_id in ids]
