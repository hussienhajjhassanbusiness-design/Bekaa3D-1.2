"""The administrator marks an STL line sent (VS-023b, ADR-019 d4). One transaction, the
caller's: lock, transition, history, audit, notice. Nothing external happens inside it."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.fulfillment.application.ports import DeliveryNotices, DeliveryOrders
from app.ordering.public import LineNotFoundError, OrderStatus
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class DeliveryResult:
    order_id: UUID
    item_id: UUID
    fulfilled_at: datetime
    delivered_by: UUID
    order_status: OrderStatus


async def mark_stl_delivered(
    orders: DeliveryOrders,
    audit: AuditWriter,
    notices: DeliveryNotices,
    *,
    order_id: UUID,
    item_id: UUID,
    admin_id: UUID,
    at: datetime,
    request_id: str | None,
    ip_hash: str | None,
) -> DeliveryResult:
    locked = await orders.lock(order_id)
    if locked is None:
        raise LineNotFoundError(f"order {order_id} does not exist")
    line, order_status = await orders.mark_delivered(
        locked, line_id=item_id, admin_id=admin_id, at=at
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
            "order_id": str(order_id),
            "order_number": locked.order.order_number,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    await notices.stl_delivered(locked, line)
    return DeliveryResult(order_id, item_id, at, admin_id, order_status)
