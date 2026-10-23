"""The adapters refunds write through, all on the caller's session: Ordering's locked order
(`ordering.public`) and the customer's "refund issued" email and notification (Q7).
Payloads carry ids and amounts only: no phone, hash, address or provider data."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.ordering.public import (
    LineState,
    LockedOrder,
    OrderItemStatus,
    OrderStatus,
    RefundFacts,
    lock_order_for_change,
    recompute_order_status,
    refund_lines,
    status_inputs_for,
)
from app.payments.application.services.refunds import RefundDeps
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.refunds import SqlRefundStore
from app.platform.public import SqlAuditWriter, SqlOutboxWriter

REFUND_TEMPLATE = "order_refund_issued"
LINE_REFUNDED_REASON = "refund"


class SqlRefundOrders:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        return await lock_order_for_change(self._session, order_id)

    async def refund_lines(
        self, locked: LockedOrder, line_ids: tuple[UUID, ...], *, actor_user_id: UUID, at: datetime
    ) -> None:
        await refund_lines(
            self._session,
            locked,
            line_ids,
            actor_user_id=actor_user_id,
            reason=LINE_REFUNDED_REASON,
            at=at,
        )

    async def recompute(
        self,
        locked: LockedOrder,
        *,
        refunded: tuple[UUID, ...],
        refunds: RefundFacts,
        actor_user_id: UUID,
    ) -> OrderStatus:
        states = tuple(
            LineState(OrderItemStatus.REFUNDED if line.id in refunded else line.fulfillment_status)
            for line in locked.lines
        )
        return await recompute_order_status(
            self._session,
            locked,
            status_inputs_for(locked, states, reached_paid=True, refunds=refunds),
            actor_user_id=actor_user_id,
        )


class SqlRefundNotices:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def refund_issued(
        self, locked: LockedOrder, *, refund_id: UUID, amount_cents: int, currency: str
    ) -> None:
        order = locked.order
        payload = {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "refund_id": str(refund_id),
            "amount_cents": amount_cents,
            "currency": currency,
        }
        await SqlOutboxWriter(self._session).add(
            user_id=order.user_id,
            recipient_email=order.customer_email_snapshot,
            template=REFUND_TEMPLATE,
            payload=payload,
        )
        await create_notification(
            self._session,
            user_id=order.user_id,
            notification_type=NotificationType.REFUND,
            payload={"event": "refund.issued"} | payload,
        )


def refund_deps(session: AsyncSession) -> RefundDeps:
    return RefundDeps(
        orders=SqlRefundOrders(session),
        payments=SqlPaymentStore(session),
        refunds=SqlRefundStore(session),
        audit=SqlAuditWriter(session),
        notices=SqlRefundNotices(session),
    )
