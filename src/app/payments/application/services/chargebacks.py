"""Recording a chargeback (VS-030 plan 3.3; ADR-042 d3-d4; owner answers C1, C4), in the
caller's one transaction. Lock order (plan 8.1 path 6): orders, its lines by id, the order's
payments by id, the payment's open refunds by id, then the chargeback INSERT (rank 5)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

import structlog

from app.ordering.public import LockedOrder, OrderStatus
from app.payments.application.services.refunds import AuditContext, RefundDeps
from app.payments.domain.alerts import AlertKind, repeat_window
from app.payments.domain.chargebacks import (
    Allocation,
    NewChargeback,
    allocate_late,
    allocate_paid,
)
from app.payments.domain.enums import PaymentProvider, RefundStatus
from app.payments.domain.exceptions import (
    ChargebackDuplicateError,
    ChargebackItemsForbiddenError,
    ChargebackNotOnlineError,
    OrderNotPaidError,
    RefundNotFoundError,
)
from app.payments.domain.outcome import REACHED_PAID
from app.payments.domain.payments import Payment
from app.payments.domain.refunds import (
    ChargebackFact,
    ItemFact,
    Ledger,
    LineFact,
    NewRefund,
    PaymentFact,
    Refund,
    check_order_totals,
    payment_status,
    refund_facts,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class ChargebackOutcome:
    chargeback_id: UUID
    allocation: Allocation
    order_status: OrderStatus | None  # None: a late-captured attempt moves no status


async def record_chargeback(
    deps: RefundDeps,
    *,
    order_id: UUID,
    payment_id: UUID,
    dispute_reference: str,
    charged_cents: int,
    items: Sequence[ItemFact],
    reason: str,
    received_at: datetime,
    ctx: AuditContext,
    at: datetime,
) -> ChargebackOutcome:
    """Void the payment's open refunds, absorbing them into the chargeback (C1), add the
    admin's items, move the emptied lines (D4), recompute both statuses, audit and alert."""
    locked = await deps.orders.lock(order_id)  # ranks 1 and 2
    if locked is None:
        raise RefundNotFoundError(f"order {order_id} does not exist")
    attempts = await deps.payments.lock_for_order(order_id)  # rank 3, by id
    payment = next((p for p in attempts if p.id == payment_id), None)
    if payment is None:
        raise RefundNotFoundError(f"payment {payment_id} is not on order {order_id}")
    if payment.provider is PaymentProvider.CASH:
        raise ChargebackNotOnlineError("a cash payment cannot be charged back")
    paid = payment.status in REACHED_PAID
    if not paid and payment.late_captured_at is None:
        raise OrderNotPaidError(f"payment {payment_id} never took money")
    if not paid and items:
        raise ChargebackItemsForbiddenError("a late-captured attempt paid no line")
    if await deps.chargebacks.dispute_exists(payment.provider, dispute_reference):
        raise ChargebackDuplicateError("this dispute reference is already recorded")
    known = {line.id for line in locked.lines}
    if any(item.order_item_id not in known for item in items):
        raise RefundNotFoundError(f"a line is not on order {order_id}")
    rows = await deps.refunds.for_order(order_id)  # after rank 1: every writer holds it
    ledger = Ledger(
        order_total_cents=locked.order.total_cents,
        lines=tuple(
            LineFact(line.id, line.product_type, line.fulfillment_status, line.line_total_cents)
            for line in locked.lines
        ),
        payment=PaymentFact(
            payment.id, payment.provider, payment.status, payment.amount_cents, payment.currency
        ),
        refunds=tuple(row.fact() for row in rows),
        chargebacks=tuple(await deps.chargebacks.for_order(order_id)),
    )
    if paid:  # Q-2 guards the balances; a late-captured attempt derives none
        check_order_totals(ledger, order_currency=locked.order.currency)
    open_refunds = await deps.refunds.lock_open_for_payment(payment_id)  # rank 4, by id
    if paid:
        allocation = allocate_paid(ledger, open_refunds, charged_cents=charged_cents, items=items)
    else:
        allocation = allocate_late(open_refunds, charged_cents=charged_cents)
    chargeback_id = uuid4()
    remainders = await _void_and_remainders(deps, allocation, open_refunds, chargeback_id, ctx, at)
    await deps.chargebacks.insert(  # rank 5
        NewChargeback(
            id=chargeback_id,
            order_id=order_id,
            payment_id=payment_id,
            provider=payment.provider,
            dispute_reference=dispute_reference,
            charged_cents=charged_cents,
            applied_cents=allocation.applied_cents,
            excess_cents=allocation.excess_cents,
            reason=reason,
            recorded_by=ctx.actor_user_id,
            received_at=received_at,
            items=allocation.items,
        )
    )
    status = None
    if paid:
        status = await _move_and_recompute(
            deps, locked, payment, ledger, allocation, remainders, ctx=ctx, at=at
        )
    await _audit_and_alert(
        deps, locked, payment, chargeback_id, allocation, remainders, charged_cents, reason, ctx
    )
    return ChargebackOutcome(chargeback_id, allocation, status)


async def _void_and_remainders(
    deps: RefundDeps,
    allocation: Allocation,
    open_refunds: Sequence[Refund],
    chargeback_id: UUID,
    ctx: AuditContext,
    at: datetime,
) -> list[Refund]:
    """The absorbed refunds become `voided`; what the bank left owed is a new pending one.
    Each gets its own audit row, so a refund's history is complete on its own."""
    by_id = {r.id: r for r in open_refunds}
    for refund_id in allocation.voided:
        reason = f"absorbed by chargeback {chargeback_id}"
        if not await deps.refunds.void(refund_id, by=ctx.actor_user_id, at=at, reason=reason):
            raise RuntimeError(f"refund {refund_id} left its open state under the lock")
        await _refund_audit(
            deps,
            ctx,
            "refund.voided",
            by_id[refund_id],
            before={"status": by_id[refund_id].status.value},
            after={"status": RefundStatus.VOIDED.value, "reason": reason},
        )
    created: list[Refund] = []
    for remainder in allocation.remainders:
        source = by_id[remainder.source.id]
        new = NewRefund(
            order_id=source.order_id,
            payment_id=source.payment_id,
            provider=source.provider,
            kind=source.kind,
            items=remainder.items,
            currency=source.currency,
            reason=f"remainder after chargeback {chargeback_id}",
            requested_by=ctx.actor_user_id,
            approved_by=ctx.actor_user_id,
            initiated_at=at,
            late_amount_cents=None if remainder.items else remainder.amount_cents,
        )
        refund_id = await deps.refunds.insert(new)
        row = Refund(
            refund_id,
            new.order_id,
            new.payment_id,
            new.provider,
            new.kind,
            RefundStatus.PENDING,
            new.amount_cents,
            new.currency,
            None,
            new.items,
        )
        created.append(row)
        await _refund_audit(
            deps,
            ctx,
            "refund.created",
            row,
            before=None,
            after={
                "status": RefundStatus.PENDING.value,
                "kind": new.kind.value,
                "reason": new.reason,
            },
        )
    return created


async def _refund_audit(
    deps: RefundDeps,
    ctx: AuditContext,
    action: str,
    refund: Refund,
    *,
    before: dict[str, object] | None,
    after: dict[str, object],
) -> None:
    await deps.audit.record(
        actor_user_id=ctx.actor_user_id,
        action=action,
        entity_type="refund",
        entity_id=refund.id,
        before_data=before,
        after_data=after | {"order_id": str(refund.order_id), "amount_cents": refund.amount_cents},
        request_id=ctx.request_id,
        ip_hash=ctx.ip_hash,
    )


async def _move_and_recompute(
    deps: RefundDeps,
    locked: LockedOrder,
    payment: Payment,
    ledger: Ledger,
    allocation: Allocation,
    remainders: Sequence[Refund],
    *,
    ctx: AuditContext,
    at: datetime,
) -> OrderStatus:
    await deps.orders.chargeback_lines(
        locked,
        refunded=allocation.refunded,
        cancelled=allocation.cancelled,
        actor_user_id=ctx.actor_user_id,
        at=at,
    )
    voided = set(allocation.voided)
    refunds = tuple(
        replace(r, status=RefundStatus.VOIDED) if r.id in voided else r for r in ledger.refunds
    )
    after = replace(
        ledger,
        refunds=(*refunds, *(r.fact() for r in remainders)),
        chargebacks=(
            *ledger.chargebacks,
            ChargebackFact(payment.id, allocation.applied_cents, allocation.items),
        ),
    )
    facts = refund_facts(after)
    target = payment_status(facts)
    if target is not payment.status:
        await deps.payments.mark_status(payment.id, target, at=at)
    return await deps.orders.recompute(
        locked,
        refunded=allocation.refunded,
        cancelled=allocation.cancelled,
        refunds=facts,
        actor_user_id=ctx.actor_user_id,
    )


async def _audit_and_alert(
    deps: RefundDeps,
    locked: LockedOrder,
    payment: Payment,
    chargeback_id: UUID,
    allocation: Allocation,
    remainders: Sequence[Refund],
    charged_cents: int,
    reason: str,
    ctx: AuditContext,
) -> None:
    """Ids, amounts and the admin's reason only: never the dispute reference or a phone."""
    await deps.audit.record(
        actor_user_id=ctx.actor_user_id,
        action="chargeback.recorded",
        entity_type="chargeback",
        entity_id=chargeback_id,
        after_data={
            "order_id": str(locked.order.id),
            "payment_id": str(payment.id),
            "charged_cents": charged_cents,
            "applied_cents": allocation.applied_cents,
            "excess_cents": allocation.excess_cents,
            "items": [
                {"order_item_id": str(i.order_item_id), "amount_cents": i.amount_cents}
                for i in allocation.items
            ],
            "voided_refund_ids": [str(i) for i in allocation.voided],
            "remainder_refund_ids": [str(r.id) for r in remainders],
            "lines_refunded": [str(i) for i in allocation.refunded],
            "lines_cancelled": [str(i) for i in allocation.cancelled],
            "reason": reason,
        },
        request_id=ctx.request_id,
        ip_hash=ctx.ip_hash,
    )
    kind = AlertKind.CHARGEBACK_EXCESS if allocation.excess_cents else AlertKind.CHARGEBACK
    await deps.alerts.raise_alert(
        kind,
        payment_id=payment.id,
        order_id=locked.order.id,
        details={
            "order_number": locked.order.order_number,
            "chargeback_id": str(chargeback_id),
            "charged_cents": charged_cents,
            "applied_cents": allocation.applied_cents,
            "excess_cents": allocation.excess_cents,
        },
        dedupe_window=repeat_window(kind),
    )
    log = logger.aerror if allocation.excess_cents else logger.ainfo
    await log(
        "chargeback_excess" if allocation.excess_cents else "chargeback_recorded",
        chargeback_id=str(chargeback_id),
        order_id=str(locked.order.id),
    )
