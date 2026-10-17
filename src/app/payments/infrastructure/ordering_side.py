"""The adapters verification writes through: Ordering's locked order (`ordering.public`)
and the customer's confirmation (outbox email and in-app notification), all on the
caller's session, so they commit or roll back with the payment."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.engagement.public import NotificationType, create_notification
from app.ordering.public import (
    LineState,
    LockedOrder,
    OrderItemStatus,
    OrderStatusInputs,
    lock_order_for_change,
    mark_order_paid,
    recompute_order_status,
)
from app.platform.public import SqlOutboxWriter

CONFIRMATION_TEMPLATE = "order_payment_confirmed"


class SqlOrderSide:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        return await lock_order_for_change(self._session, order_id)

    async def mark_paid(self, locked: LockedOrder, *, at: datetime) -> tuple[UUID, ...]:
        """STL lines `pending -> awaiting_delivery` in this transaction (ADR-019 d2)."""
        moved = tuple(
            line.id
            for line in locked.lines
            if line.product_type is ProductType.STL
            and line.fulfillment_status is OrderItemStatus.PENDING
        )
        await mark_order_paid(self._session, locked, at=at)
        return moved

    async def recompute_unpaid(self, locked: LockedOrder) -> None:
        order = locked.order
        await recompute_order_status(
            self._session,
            locked,
            OrderStatusInputs(
                payment_method=order.payment_method,
                cancelled_at_set=order.cancelled_at is not None,
                payment_reached_paid=False,
                lines=tuple(LineState(line.fulfillment_status) for line in locked.lines),
            ),
        )


class SqlPaymentNotices:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def payment_confirmed(self, locked: LockedOrder) -> None:
        """To the email captured at checkout; the file itself is VS-023b's delivery."""
        order = locked.order
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=CONFIRMATION_TEMPLATE,
            payload={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "total_cents": order.total_cents,
                "currency": order.currency,
            },
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.PAYMENT,
            payload={
                "event": "payment.confirmed",
                "order_id": str(order.id),
                "order_number": order.order_number,
            },
        )
