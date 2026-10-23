"""Refund use cases (VS-030 plan 3.3): create, settle, fail, reissue and void, each in the
caller's one transaction. Lock order (plan 8.1): orders, its lines by id, the order's
payments by id, then the refund. PR C adds chargebacks at the reserved rank 5."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

import structlog

from app.ordering.public import LockedOrder, OrderItemStatus, OrderStatus
from app.payments.application.ports import PaymentStore, RefundNotices, RefundOrders, RefundStore
from app.payments.domain.enums import RefundKind, RefundStatus
from app.payments.domain.exceptions import (
    OrderNotPaidError,
    RefundNotFoundError,
    RefundRefusedError,
)
from app.payments.domain.payments import Payment
from app.payments.domain.refunds import (
    ItemFact,
    Ledger,
    LineFact,
    NewRefund,
    PaymentFact,
    Refund,
    RefundAction,
    check_order_totals,
    check_request,
    lines_becoming_refunded,
    paid_payment,
    payment_status,
    refund_facts,
    refund_step,
)
from app.platform.application.ports import AuditWriter

logger = structlog.get_logger()

# Q7: the "refund issued" notice goes out at creation for these kinds only.
NOTICE_KINDS = frozenset({RefundKind.ADMIN, RefundKind.CANCELLATION})


@dataclass(frozen=True)
class RefundDeps:
    orders: RefundOrders
    payments: PaymentStore
    refunds: RefundStore
    audit: AuditWriter
    notices: RefundNotices


@dataclass(frozen=True)
class AuditContext:
    actor_user_id: UUID
    request_id: str | None = None
    ip_hash: str | None = None


@dataclass(frozen=True)
class RefundOutcome:
    refund_id: UUID
    changed: bool  # False: an idempotent repeat, nothing written
    order_status: OrderStatus | None = None


@dataclass(frozen=True)
class _Locked:
    """Ranks 1-3 held; the refund rows were read after them."""

    order: LockedOrder
    paid: Payment
    ledger: Ledger


async def _lock(deps: RefundDeps, order_id: UUID) -> _Locked:
    locked = await deps.orders.lock(order_id)  # ranks 1 and 2
    if locked is None:
        raise RefundNotFoundError(f"order {order_id} does not exist")
    attempts = await deps.payments.lock_for_order(order_id)  # rank 3, by id
    facts = {p.id: PaymentFact(p.id, p.provider, p.status, p.amount_cents) for p in attempts}
    paid_fact = paid_payment(facts.values())
    if paid_fact is None:
        raise OrderNotPaidError(f"order {order_id} has no payment that reached paid")
    paid = next(p for p in attempts if p.id == paid_fact.id)
    rows = await deps.refunds.for_order(order_id)  # after rank 1: every writer holds it
    ledger = Ledger(
        order_total_cents=locked.order.total_cents,
        lines=tuple(
            LineFact(line.id, line.product_type, line.fulfillment_status, line.line_total_cents)
            for line in locked.lines
        ),
        payment=paid_fact,
        refunds=tuple(row.fact() for row in rows),
    )
    check_order_totals(ledger)  # Q-2: nothing is written past a mismatch
    return _Locked(locked, paid, ledger)


async def _recompute(
    deps: RefundDeps,
    held: _Locked,
    ledger: Ledger,
    *,
    refunded: tuple[UUID, ...],
    actor_user_id: UUID,
    at: datetime,
) -> OrderStatus:
    """Both projections from the rows as they now stand (never on settle)."""
    facts = refund_facts(ledger)
    target = payment_status(facts)
    if target is not held.paid.status:
        await deps.payments.mark_status(held.paid.id, target, at=at)
    return await deps.orders.recompute(
        held.order, refunded=refunded, refunds=facts, actor_user_id=actor_user_id
    )


def _with_lines(ledger: Ledger, refunded: tuple[UUID, ...]) -> Ledger:
    lines = tuple(
        replace(line, status=OrderItemStatus.REFUNDED) if line.id in refunded else line
        for line in ledger.lines
    )
    return replace(ledger, lines=lines)


async def create_refund(
    deps: RefundDeps,
    *,
    order_id: UUID,
    kind: RefundKind,
    items: Sequence[ItemFact],
    reason: str,
    ctx: AuditContext,
    at: datetime,
    cancelling: frozenset[UUID] = frozenset(),
) -> RefundOutcome:
    """L0-L8 under the locks, then the refund, the covered lines, both statuses, audit and
    (admin, cancellation) the customer's notice. `cancelling`: VS-031's lines."""
    held = await _lock(deps, order_id)
    known = {line.id for line in held.order.lines}
    if any(item.order_item_id not in known for item in items):
        raise RefundNotFoundError(f"a line is not on order {order_id}")
    check_request(held.ledger, items, cancelling=cancelling)
    covered = tuple(i for i in lines_becoming_refunded(held.ledger, items) if i not in cancelling)
    new = NewRefund(
        order_id=order_id,
        payment_id=held.paid.id,
        provider=held.paid.provider,
        kind=kind,
        items=tuple(sorted(items, key=lambda item: str(item.order_item_id))),
        currency=held.order.order.currency,
        reason=reason,
        requested_by=ctx.actor_user_id,
        approved_by=ctx.actor_user_id,
        initiated_at=at,
    )
    refund_id = await deps.refunds.insert(new)
    if covered:
        await deps.orders.refund_lines(held.order, covered, actor_user_id=ctx.actor_user_id, at=at)
    pending = Refund(
        refund_id,
        order_id,
        new.payment_id,
        new.provider,
        kind,
        RefundStatus.PENDING,
        new.amount_cents,
        new.currency,
        None,
        new.items,
    )
    after = replace(
        _with_lines(held.ledger, covered), refunds=(*held.ledger.refunds, pending.fact())
    )
    status = await _recompute(
        deps, held, after, refunded=covered, actor_user_id=ctx.actor_user_id, at=at
    )
    await _audit(
        deps,
        ctx,
        "refund.created",
        refund_id,
        before=None,
        after={
            "status": RefundStatus.PENDING.value,
            "kind": kind.value,
            "order_id": str(order_id),
            "order_number": held.order.order.order_number,
            "payment_id": str(new.payment_id),
            "amount_cents": new.amount_cents,
            "items": [
                {"order_item_id": str(i.order_item_id), "amount_cents": i.amount_cents}
                for i in new.items
            ],
            "lines_refunded": [str(i) for i in covered],
            "reason": reason,
        },
    )
    if kind in NOTICE_KINDS:
        await deps.notices.refund_issued(
            held.order, refund_id=refund_id, amount_cents=new.amount_cents, currency=new.currency
        )
    await logger.ainfo("refund_created", refund_id=str(refund_id), order_id=str(order_id))
    return RefundOutcome(refund_id, True, status)


async def _locked_refund(deps: RefundDeps, refund_id: UUID) -> tuple[_Locked, Refund]:
    seen = await deps.refunds.get(refund_id)  # unlocked: only the order id
    if seen is None:
        raise RefundNotFoundError(f"refund {refund_id} does not exist")
    held = await _lock(deps, seen.order_id)
    row = await deps.refunds.lock(refund_id)  # rank 4
    if row is None or row.order_id != seen.order_id:
        raise RefundNotFoundError(f"refund {refund_id} vanished")
    return held, row


def _decide(row: Refund, action: RefundAction, *, line_refunded: bool = False) -> bool:
    """True to write; False for an idempotent repeat; refusals raise."""
    step = refund_step(
        row.status, action, reissued=row.reissued_at is not None, line_refunded=line_refunded
    )
    if step.refusal is not None:
        raise RefundRefusedError(step.refusal.value)
    return step.target is not None


async def settle_refund(
    deps: RefundDeps,
    *,
    refund_id: UUID,
    reference: str | None,
    note: str | None,
    ctx: AuditContext,
    at: datetime,
) -> RefundOutcome:
    """`pending -> settled`; no order or payment status changes (ADR-024 d12)."""
    _, row = await _locked_refund(deps, refund_id)
    if not _decide(row, RefundAction.SETTLE):
        return RefundOutcome(refund_id, False)
    if not await deps.refunds.settle(
        refund_id, by=ctx.actor_user_id, at=at, reference=reference, note=note
    ):
        raise RefundRefusedError("not_pending")
    await _audit(
        deps,
        ctx,
        "refund.settled",
        refund_id,
        before={"status": row.status.value},
        after={
            "status": RefundStatus.SETTLED.value,
            "order_id": str(row.order_id),
            "amount_cents": row.amount_cents,
        },
    )
    return RefundOutcome(refund_id, True)


async def fail_refund(
    deps: RefundDeps, *, refund_id: UUID, reason: str, ctx: AuditContext, at: datetime
) -> RefundOutcome:
    """`pending -> failed`: still owed, so the order reads `partially_refunded`."""
    held, row = await _locked_refund(deps, refund_id)
    if not _decide(row, RefundAction.FAIL):
        return RefundOutcome(refund_id, False)
    if not await deps.refunds.fail(refund_id, by=ctx.actor_user_id, at=at, reason=reason):
        raise RefundRefusedError("not_pending")
    status = await _recompute(
        deps,
        held,
        _replace_refund(held.ledger, replace(row, status=RefundStatus.FAILED)),
        refunded=(),
        actor_user_id=ctx.actor_user_id,
        at=at,
    )
    await _audit(
        deps,
        ctx,
        "refund.failed",
        refund_id,
        before={"status": row.status.value},
        after={
            "status": RefundStatus.FAILED.value,
            "order_id": str(row.order_id),
            "amount_cents": row.amount_cents,
            "reason": reason,
        },
    )
    return RefundOutcome(refund_id, True, status)


async def void_refund(
    deps: RefundDeps, *, refund_id: UUID, reason: str, ctx: AuditContext, at: datetime
) -> RefundOutcome:
    """`pending`, or `failed` not reissued, -> `voided`; never after settlement, never on a
    refund with a line already `refunded`. A repeat keeps the first reason, no new audit."""
    held, row = await _locked_refund(deps, refund_id)
    states = {line.id: line.fulfillment_status for line in held.order.lines}
    line_refunded = any(states.get(i.order_item_id) is OrderItemStatus.REFUNDED for i in row.items)
    if not _decide(row, RefundAction.VOID, line_refunded=line_refunded):
        return RefundOutcome(refund_id, False)
    if not await deps.refunds.void(refund_id, by=ctx.actor_user_id, at=at, reason=reason):
        raise RefundRefusedError("already_settled")
    status = await _recompute(
        deps,
        held,
        _replace_refund(held.ledger, replace(row, status=RefundStatus.VOIDED)),
        refunded=(),
        actor_user_id=ctx.actor_user_id,
        at=at,
    )
    await _audit(
        deps,
        ctx,
        "refund.voided",
        refund_id,
        before={"status": row.status.value},
        after={
            "status": RefundStatus.VOIDED.value,
            "reason": reason,
            "order_id": str(row.order_id),
            "amount_cents": row.amount_cents,
        },
    )
    return RefundOutcome(refund_id, True, status)


async def reissue_refund(
    deps: RefundDeps, *, refund_id: UUID, ctx: AuditContext, at: datetime
) -> RefundOutcome:
    """A failed, not reissued refund gets a new `pending` twin (same kind, items, amount);
    its items were reserved, so no balance re-check. No customer notice (Q7)."""
    held, row = await _locked_refund(deps, refund_id)
    _decide(row, RefundAction.REISSUE)  # a reissue is never a silent repeat
    new = NewRefund(
        order_id=row.order_id,
        payment_id=row.payment_id,
        provider=row.provider,
        kind=row.kind,
        items=row.items,
        currency=row.currency,
        reason=f"reissue of {row.id}",
        requested_by=ctx.actor_user_id,
        approved_by=ctx.actor_user_id,
        initiated_at=at,
        reissue_of_refund_id=row.id,
    )
    new_id = await deps.refunds.insert(new)
    if not await deps.refunds.mark_reissued(refund_id, at=at):
        raise RefundRefusedError("already_reissued")
    twin = Refund(
        new_id,
        row.order_id,
        row.payment_id,
        row.provider,
        row.kind,
        RefundStatus.PENDING,
        row.amount_cents,
        row.currency,
        None,
        row.items,
    )
    ledger = _replace_refund(held.ledger, replace(row, reissued_at=at))
    status = await _recompute(
        deps,
        held,
        replace(ledger, refunds=(*ledger.refunds, twin.fact())),
        refunded=(),
        actor_user_id=ctx.actor_user_id,
        at=at,
    )
    await _audit(
        deps,
        ctx,
        "refund.reissued",
        refund_id,
        before={"status": row.status.value},
        after={
            "reissued_by_refund_id": str(new_id),
            "order_id": str(row.order_id),
            "amount_cents": row.amount_cents,
        },
    )
    return RefundOutcome(new_id, True, status)


def _replace_refund(ledger: Ledger, row: Refund) -> Ledger:
    return replace(
        ledger, refunds=tuple(row.fact() if r.id == row.id else r for r in ledger.refunds)
    )


async def _audit(
    deps: RefundDeps,
    ctx: AuditContext,
    action: str,
    refund_id: UUID,
    *,
    before: dict[str, object] | None,
    after: dict[str, object],
) -> None:
    """Ids, amounts, states and the admin's reason only: no phone, hash or provider data."""
    await deps.audit.record(
        actor_user_id=ctx.actor_user_id,
        action=action,
        entity_type="refund",
        entity_id=refund_id,
        before_data=before,
        after_data=after,
        request_id=ctx.request_id,
        ip_hash=ctx.ip_hash,
    )
