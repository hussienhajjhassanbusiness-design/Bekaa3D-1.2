"""The adapters verification writes through: Ordering's locked order (`ordering.public`)
and the customer's confirmation (outbox email and in-app notification), all on the
caller's session, so they commit or roll back with the payment."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.engagement.public import NotificationType, create_notification
from app.negotiation.public import StlPurchase, settle_offers_on_stl_purchase
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
RELEASE_TEMPLATE = "order_checkout_expired"


class SqlOrderSide:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        return await lock_order_for_change(self._session, order_id)

    async def mark_paid(self, locked: LockedOrder, *, at: datetime) -> tuple[UUID, ...]:
        """STL lines `pending -> awaiting_delivery` and their offers settled, in this
        transaction (ADR-019 d2, ADR-037)."""
        moved = [
            line
            for line in locked.lines
            if line.product_type is ProductType.STL
            and line.fulfillment_status is OrderItemStatus.PENDING
        ]
        await mark_order_paid(self._session, locked, at=at)
        # BR-088, SRS 5.4 step 6: after the orders, lines and payment locks (ADR-037).
        await settle_offers_on_stl_purchase(
            self._session,
            [
                StlPurchase(line.order_id, line.user_id, line.product_id, line.offer_id)
                for line in moved
            ],
            at=at,
        )
        return tuple(line.id for line in moved)

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

    async def checkout_released(self, locked: LockedOrder) -> None:
        """VS-024 owner question 5: the hold ended unpaid; a late payment is refunded."""
        order = locked.order
        payload = {"order_id": str(order.id), "order_number": order.order_number}
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=RELEASE_TEMPLATE,
            payload=payload,
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.ORDER,
            payload={"event": "order.checkout_expired"} | payload,
        )
