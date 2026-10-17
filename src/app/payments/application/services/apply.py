"""Applying one provider answer to a payment (VS-023 plan 3.6; SRS 9.2, 20.1). Tx B of
verification, and VS-024's manual confirm. Locks, in this order and no others: the
order, its lines by id (`OrderSide.lock`), then the payment (ADR-024 d9)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import structlog

from app.ordering.public import LockedOrder
from app.payments.application.ports import OrderSide, PaymentNotices, PaymentStore
from app.payments.domain.enums import PaymentStatus
from app.payments.domain.exceptions import PaymentNotFoundError
from app.payments.domain.outcome import LIVE, Outcome, ProviderResult, decide
from app.payments.domain.payments import Payment
from app.platform.application.ports import AuditWriter

logger = structlog.get_logger()

Source = Literal["webhook", "reconcile", "manual"]


async def apply_result(
    *,
    payments: PaymentStore,
    orders: OrderSide,
    audit: AuditWriter,
    notices: PaymentNotices,
    payment_id: UUID,
    result: ProviderResult,
    source: Source,
    actor_user_id: UUID | None,
    provider_payment_id: str | None,
    at: datetime,
) -> Outcome:
    """Decide from the locked rows, then write. A missing `provider_payment_id` (the
    checkout Tx2 crash) is stored here, under the same locks (Revision 5 item 1)."""
    seen = await payments.get(payment_id)  # unlocked: only to learn the order id
    if seen is None:
        raise PaymentNotFoundError(f"payment {payment_id} does not exist")
    locked = await orders.lock(seen.order_id)
    payment = await payments.lock(payment_id)
    if locked is None or payment is None:
        raise PaymentNotFoundError(f"payment {payment_id} or its order vanished")
    if provider_payment_id is not None and payment.provider_payment_id is None:
        await payments.fill_provider_reference(payment_id, provider_payment_id, at=at)

    order = locked.order
    outcome = decide(
        payment_status=payment.status,
        payment_amount_cents=payment.amount_cents,
        order_total_cents=order.total_cents,
        order_cancelled=order.cancelled_at is not None,
        already_late_captured=payment.late_captured_at is not None,
        result=result,
    )
    if outcome is Outcome.APPLY_PAID:
        await _paid(payments, orders, audit, notices, locked, payment, source, at)
    elif outcome in (Outcome.MARK_FAILED, Outcome.MARK_EXPIRED, Outcome.MARK_PROCESSING):
        await _status(payments, orders, audit, locked, payment, outcome, source, at)
    elif outcome in (Outcome.LATE_CAPTURE, Outcome.LATE_CAPTURE_AND_FAIL):
        await _late_capture(payments, audit, locked, payment, outcome, result, source, at)
    return outcome


async def _paid(
    payments: PaymentStore,
    orders: OrderSide,
    audit: AuditWriter,
    notices: PaymentNotices,
    locked: LockedOrder,
    payment: Payment,
    source: Source,
    at: datetime,
) -> None:
    await payments.mark_paid(payment.id, at=at)
    moved = await orders.mark_paid(locked, at=at)
    order = locked.order
    await audit.record(
        actor_user_id=None,
        action="payment.verified",
        entity_type="payment",
        entity_id=payment.id,
        after_data={
            "order_id": str(order.id),
            "order_number": order.order_number,
            "amount_cents": payment.amount_cents,
            "lines_awaiting_delivery": [str(line_id) for line_id in moved],
            "source": source,
        },
    )
    await notices.payment_confirmed(locked)


_STATUS = {
    Outcome.MARK_FAILED: (PaymentStatus.FAILED, "payment.failed"),
    Outcome.MARK_EXPIRED: (PaymentStatus.EXPIRED, "payment.expired"),
    Outcome.MARK_PROCESSING: (PaymentStatus.PROCESSING, None),
}


async def _status(
    payments: PaymentStore,
    orders: OrderSide,
    audit: AuditWriter,
    locked: LockedOrder,
    payment: Payment,
    outcome: Outcome,
    source: Source,
    at: datetime,
) -> None:
    """The order stays `pending_payment` (BR-058); the projection is recomputed anyway."""
    status, action = _STATUS[outcome]
    await payments.mark_status(payment.id, status, at=at)
    if action is not None:
        await audit.record(
            actor_user_id=None,
            action=action,
            entity_type="payment",
            entity_id=payment.id,
            after_data={"order_id": str(locked.order.id), "source": source},
        )
    await orders.recompute_unpaid(locked)


async def _late_capture(
    payments: PaymentStore,
    audit: AuditWriter,
    locked: LockedOrder,
    payment: Payment,
    outcome: Outcome,
    result: ProviderResult,
    source: Source,
    at: datetime,
) -> None:
    """Money arrived that must not pay the order: recorded once, lines untouched. VS-030
    turns these into refund obligations (`ix_payments_late_captured`)."""
    order = locked.order
    if payment.status not in LIVE:
        reason = "attempt_not_live"
    elif order.cancelled_at is not None:
        reason = "order_cancelled"
    else:
        reason = "amount_mismatch"
    await payments.mark_late_capture(
        payment.id, at=at, fail=outcome is Outcome.LATE_CAPTURE_AND_FAIL
    )
    details: dict[str, Any] = {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "captured_amount_cents": result.captured_amount_cents,
        "captured_currency": result.currency,
        "expected_amount_cents": payment.amount_cents,
        "attempt_status": payment.status.value,
        "reason": reason,
        "source": source,
    }
    await audit.record(
        actor_user_id=None,
        action="payment.late_capture",
        entity_type="payment",
        entity_id=payment.id,
        after_data=details,
    )
    await logger.aerror(
        "payment_late_capture", payment_id=str(payment.id), order_id=str(order.id), reason=reason
    )
