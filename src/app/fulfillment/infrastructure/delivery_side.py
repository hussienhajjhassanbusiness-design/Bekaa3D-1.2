"""The adapters the delivery use case writes through, all on the route's session so they
commit or roll back together. The email is an outbox row; `dispatch_outbox` sends it."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.ordering.public import (
    LockedOrder,
    OrderLine,
    OrderStatus,
    lock_order_for_change,
    mark_stl_line_delivered,
)
from app.platform.public import SqlOutboxWriter

DELIVERED_TEMPLATE = "order_stl_delivered"


class SqlDeliveryOrders:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        return await lock_order_for_change(self._session, order_id)

    async def mark_delivered(
        self, locked: LockedOrder, *, line_id: UUID, admin_id: UUID, at: datetime
    ) -> tuple[OrderLine, OrderStatus]:
        return await mark_stl_line_delivered(
            self._session, locked, line_id=line_id, admin_id=admin_id, at=at
        )


class SqlDeliveryNotices:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def stl_delivered(self, locked: LockedOrder, line: OrderLine) -> None:
        order = locked.order
        payload = {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "item_id": str(line.id),
            "product_name": line.product_name_snapshot,
        }
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=DELIVERED_TEMPLATE,
            payload=payload,
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.DOWNLOAD,
            payload={"event": "stl.delivered"} | payload,
        )
