"""Ordering's customer notices, on the caller's session so they commit with the order."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.ordering.domain.cash import amount_due_cents
from app.ordering.domain.enums import FulfillmentMethod
from app.ordering.domain.fulfillment import DELIVERY_FEE_NOTE
from app.ordering.domain.orders import Order, OrderLine
from app.platform.public import SqlOutboxWriter

CASH_PLACED_TEMPLATE = "order_cash_placed"
AWAITING_PAYMENT_TEMPLATE = "order_awaiting_payment"


class SqlOrderNotices:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cash_order_placed(self, order: Order, lines: Sequence[OrderLine]) -> None:
        """No phone and no address in the payload: the outbox row is stored."""
        method = order.fulfillment_method
        eta = order.estimated_dispatch_at
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=CASH_PLACED_TEMPLATE,
            payload={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "amount_due_cents": amount_due_cents(lines),
                "currency": order.currency,
                "fulfillment_method": method.value if method else None,
                "estimated_dispatch_at": eta.isoformat() if eta else None,
                "delivery_fee_note": DELIVERY_FEE_NOTE
                if method is FulfillmentMethod.DELIVERY
                else None,
                "pickup": method is FulfillmentMethod.PICKUP,
            },
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.ORDER,
            payload={
                "event": "order.placed",
                "order_id": str(order.id),
                "order_number": order.order_number,
            },
        )

    async def awaiting_admin_contact(self, order: Order) -> None:
        """ADR-049: placed, and the administrator will contact the customer to arrange
        payment. Neither payload carries the phone."""
        payload = {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "total_cents": order.total_cents,
            "currency": order.currency,
        }
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=AWAITING_PAYMENT_TEMPLATE,
            payload=payload,
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.ORDER,
            payload={"event": "order.awaiting_payment"} | payload,
        )
