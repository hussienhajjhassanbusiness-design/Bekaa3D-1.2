"""The administrator marks an STL line sent (VS-023b, ADR-019 d4). One transaction, the
caller's: lock, transition, history, audit, notice. Nothing external happens inside it."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.fulfillment.application.ports import DeliveryNotices, DeliveryOrders
from app.ordering.public import LockedOrder, OrderStatus, RefundFacts
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class DeliveryResult:
    order_id: UUID
    item_id: UUID
    fulfilled_at: datetime
    delivered_by: UUID
    order_status: OrderStatus


async def deliver_stl_line(
    orders: DeliveryOrders,
    audit: AuditWriter,
    notices: DeliveryNotices,
    locked: LockedOrder,
    *,
    refunds: RefundFacts,
    item_id: UUID,
    admin_id: UUID,
    at: datetime,
    note: str | None,
    request_id: str | None,
    ip_hash: str | None,
) -> DeliveryResult:
    """The delivery itself, on an order the caller has locked; `refunds` read after it."""
    line, order_status = await orders.mark_delivered(
        locked, line_id=item_id, admin_id=admin_id, at=at, refunds=refunds, note=note
    )
    await audit.record(
        actor_user_id=admin_id,
        action="stl.delivered",
        entity_type="order_item",
        entity_id=item_id,
        before_data={"fulfillment_status": "awaiting_delivery"},
        after_data={
            "fulfillment_status": "delivered",
            "fulfilled_at": at.isoformat(),
            "delivered_by": str(admin_id),
            "order_id": str(locked.order.id),
            "order_number": locked.order.order_number,
            "note": note,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    await notices.stl_delivered(locked, line)
    return DeliveryResult(locked.order.id, item_id, at, admin_id, order_status)
