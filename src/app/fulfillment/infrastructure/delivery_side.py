"""The adapters Fulfillment's use cases write through, all on the route's session so they
commit or roll back together. Emails are outbox rows; `dispatch_outbox` sends them."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.ordering.public import (
    DELIVERY_FEE_NOTE,
    CancelReason,
    FulfillmentMethod,
    LineCancel,
    LineState,
    LockedOrder,
    OrderItemStatus,
    OrderLine,
    OrderStatus,
    RefundFacts,
    cancel_lines,
    cash_block_store,
    hand_over_cash_lines,
    lock_cart_for_cash_block,
    lock_cash_phone,
    lock_order_for_change,
    mark_stl_line_delivered,
    recompute_order_status,
    status_inputs_for,
    transition_physical_line,
)
from app.payments.public import (
    CancellationRefund,
    OrderPaymentRow,
    create_cancellation_refund,
    insert_cash_payment,
    order_payment_reader,
    order_payment_rows,
    order_refund_facts,
)
from app.platform.public import SqlOutboxWriter, settings_reader

DELIVERED_TEMPLATE = "order_stl_delivered"
CANCELLED_TEMPLATE = "order_cancelled"
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
        self,
        locked: LockedOrder,
        *,
        line_id: UUID,
        admin_id: UUID,
        at: datetime,
        refunds: RefundFacts,
    ) -> tuple[OrderLine, OrderStatus]:
        return await mark_stl_line_delivered(
            self._session, locked, line_id=line_id, admin_id=admin_id, at=at, refunds=refunds
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
        refunds: RefundFacts,
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
            refunds=refunds,
            note=note,
        )

    async def hand_over(
        self, locked: LockedOrder, *, admin_id: UUID, at: datetime, note: str | None
    ) -> tuple[tuple[OrderLine, ...], OrderStatus]:
        return await hand_over_cash_lines(
            self._session, locked, admin_id=admin_id, at=at, note=note
        )

    async def cancel(
        self,
        locked: LockedOrder,
        cancels: tuple[LineCancel, ...],
        *,
        actor_user_id: UUID,
        at: datetime,
        note: str | None,
        by_customer: bool,
    ) -> None:
        await cancel_lines(
            self._session,
            locked,
            cancels,
            actor_user_id=actor_user_id,
            at=at,
            note=note,
            by_customer=by_customer,
        )

    async def insert_cash_block(
        self, locked: LockedOrder, *, reason: CancelReason, at: datetime
    ) -> bool:
        """After the orders lock: the cart, then the phone, so it serialises against the
        customer's checkouts with any phone and any account's with this one (ADR-024 d9)."""
        order = locked.order
        if order.contact_phone_hash is None:  # a physical order always has one (VS-028)
            raise RuntimeError(f"cash order {order.id} has no contact phone hash")
        await lock_cart_for_cash_block(self._session, order.user_id)
        await lock_cash_phone(self._session, order.contact_phone_hash)
        return await cash_block_store(self._session).insert_block(
            user_id=order.user_id,
            phone_hash=order.contact_phone_hash,
            order_id=order.id,
            reason=reason,
            at=at,
        )

    async def recompute(
        self,
        locked: LockedOrder,
        lines: tuple[LineState, ...],
        *,
        reached_paid: bool,
        refunds: RefundFacts,
        actor_user_id: UUID,
    ) -> OrderStatus:
        return await recompute_order_status(
            self._session,
            locked,
            status_inputs_for(locked, lines, reached_paid=reached_paid, refunds=refunds),
            actor_user_id=actor_user_id,
        )


class SqlOrderPayments:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reached_paid(self, order_id: UUID) -> bool:
        view = (await order_payment_reader(self._session).views([order_id])).get(order_id)
        return view is not None and view.reached_paid

    async def refund_facts(self, order_id: UUID) -> RefundFacts:
        return await order_refund_facts(self._session, order_id)

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

    async def cancellation_refund(
        self,
        locked: LockedOrder,
        cancelling: frozenset[UUID],
        *,
        actor_user_id: UUID,
        by_customer: bool,
        at: datetime,
        request_id: str | None,
        ip_hash: str | None,
    ) -> CancellationRefund | None:
        return await create_cancellation_refund(
            self._session,
            locked,
            cancelling=cancelling,
            reason="customer cancellation" if by_customer else "cancellation",
            actor_user_id=actor_user_id,
            by_customer=by_customer,
            at=at,
            request_id=request_id,
            ip_hash=ip_hash,
        )


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

    async def order_cancelled(
        self,
        locked: LockedOrder,
        cancelled: tuple[OrderLine, ...],
        *,
        order_cancelled: bool,
        amount_due_cents: int | None,
        refund_cents: int | None,
    ) -> None:
        await self._send(
            locked,
            CANCELLED_TEMPLATE,
            "order.cancelled",
            {
                "items": [
                    {"item_id": str(line.id), "product_name": line.product_name_snapshot}
                    for line in cancelled
                ],
                "order_cancelled": order_cancelled,
                "amount_due_cents": amount_due_cents,
                "refund_cents": refund_cents,
                "currency": locked.order.currency,
            },
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
