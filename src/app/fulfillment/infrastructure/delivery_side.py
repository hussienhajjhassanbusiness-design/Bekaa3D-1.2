"""The adapters Fulfillment's use cases write through, all on the route's session so they
commit or roll back together. Emails are outbox rows; `dispatch_outbox` sends them."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.ordering.public import (
    DELIVERY_FEE_NOTE,
    FulfillmentMethod,
    LockedOrder,
    OrderItemStatus,
    OrderLine,
    OrderStatus,
    hand_over_cash_lines,
    lock_order_for_change,
    mark_stl_line_delivered,
    transition_physical_line,
)
from app.payments.public import (
    OrderPaymentRow,
    insert_cash_payment,
    order_payment_reader,
    order_payment_rows,
)
from app.platform.public import SqlOutboxWriter, settings_reader

DELIVERED_TEMPLATE = "order_stl_delivered"
# One template per visible step (SRS 16.1); the handover reuses the last two.
STEP_TEMPLATES = {
    OrderItemStatus.READY_TO_SHIP: "order_ready",
    OrderItemStatus.SHIPPED: "order_shipped",
    OrderItemStatus.READY_FOR_PICKUP: "order_ready_for_pickup",
    OrderItemStatus.DELIVERED: "order_delivered",
    OrderItemStatus.PICKED_UP: "order_picked_up",
}
RECEIPT_STEPS = frozenset({OrderItemStatus.DELIVERED, OrderItemStatus.PICKED_UP})


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

    async def transition(
        self,
        locked: LockedOrder,
        *,
        line_id: UUID,
        target: OrderItemStatus,
        admin_id: UUID,
        at: datetime,
        reached_paid: bool,
        note: str | None,
    ) -> tuple[OrderLine, OrderStatus]:
        return await transition_physical_line(
            self._session,
            locked,
            line_id=line_id,
            target=target,
            admin_id=admin_id,
            at=at,
            reached_paid=reached_paid,
            note=note,
        )

    async def hand_over(
        self, locked: LockedOrder, *, admin_id: UUID, at: datetime, note: str | None
    ) -> tuple[tuple[OrderLine, ...], OrderStatus]:
        return await hand_over_cash_lines(
            self._session, locked, admin_id=admin_id, at=at, note=note
        )


class SqlOrderPayments:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reached_paid(self, order_id: UUID) -> bool:
        view = (await order_payment_reader(self._session).views([order_id])).get(order_id)
        return view is not None and view.reached_paid

    async def record_cash(
        self, *, order_id: UUID, amount_cents: int, currency: str, admin_id: UUID, at: datetime
    ) -> UUID:
        return await insert_cash_payment(
            self._session,
            order_id=order_id,
            amount_cents=amount_cents,
            currency=currency,
            recorded_by=admin_id,
            at=at,
        )

    async def rows(self, order_id: UUID) -> list[OrderPaymentRow]:
        return await order_payment_rows(self._session, order_id)


class SqlDeliveryNotices:
    """No phone, hash or customer address in any payload (notification contract)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _send(
        self, locked: LockedOrder, template: str, event: str, payload: dict[str, Any]
    ) -> None:
        order = locked.order
        payload = {"order_id": str(order.id), "order_number": order.order_number} | payload
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=template,
            payload=payload,
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.DOWNLOAD
            if event == "stl.delivered"
            else NotificationType.ORDER,
            payload={"event": event} | payload,
        )

    async def stl_delivered(self, locked: LockedOrder, line: OrderLine) -> None:
        await self._send(
            locked,
            DELIVERED_TEMPLATE,
            "stl.delivered",
            {"item_id": str(line.id), "product_name": line.product_name_snapshot},
        )

    async def step_reached(self, locked: LockedOrder, step: OrderItemStatus) -> None:
        payload = await self._step_payload(locked, step)
        await self._send(locked, STEP_TEMPLATES[step], f"order.{step.value}", payload)

    async def cash_handed_over(
        self, locked: LockedOrder, *, payment_id: UUID, amount_cents: int, recorded_at: datetime
    ) -> None:
        method = locked.order.fulfillment_method
        step = (
            OrderItemStatus.PICKED_UP
            if method is FulfillmentMethod.PICKUP
            else OrderItemStatus.DELIVERED
        )
        receipt = {
            "cash_receipt": {
                "payment_id": str(payment_id),
                "amount_cents": amount_cents,
                "currency": locked.order.currency,
                "recorded_at": recorded_at.isoformat(),
            }
        }
        payload = await self._step_payload(locked, step) | receipt
        await self._send(locked, STEP_TEMPLATES[step], f"order.{step.value}", payload)

    async def _step_payload(self, locked: LockedOrder, step: OrderItemStatus) -> dict[str, Any]:
        method = locked.order.fulfillment_method
        payload: dict[str, Any] = {
            "step": step.value,
            "fulfillment_method": method.value if method else None,
            "payment_method": locked.order.payment_method.value,
            "delivery_fee_note": DELIVERY_FEE_NOTE
            if method is FulfillmentMethod.DELIVERY
            else None,
            # The email's "I got it" / "Report a problem" buttons open the order page (8.8).
            "receipt_actions": step in RECEIPT_STEPS,
        }
        if step is OrderItemStatus.READY_FOR_PICKUP:
            settings = settings_reader(self._session)
            payload["pickup_address"] = await settings.get_text("pickup_address")
            payload["pickup_hours"] = await settings.get_text("pickup_hours")
        return payload
