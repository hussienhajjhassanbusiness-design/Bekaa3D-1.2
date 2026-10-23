"""Refund balances and the refund state machine (VS-030 plan 3.2, ADR-042). Pure: every
input is a row read after the orders lock; the lock, not this module, makes it safe."""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.application.ports import OrderItemStatus, RefundFacts
from app.payments.domain.enums import PaymentProvider, PaymentStatus, RefundKind, RefundStatus
from app.payments.domain.exceptions import (
    OrderTotalMismatchError,
    RefundExceedsAvailableError,
    RefundRequiresCancellationError,
)
from app.payments.domain.outcome import REACHED_PAID

S = OrderItemStatus
# Only a physical line can be in these on a paid order (an STL line leaves `pending` when paid).
UNFINISHED_PHYSICAL = frozenset(
    {S.PENDING, S.IN_PRODUCTION, S.READY_TO_SHIP, S.SHIPPED, S.READY_FOR_PICKUP}
)
REFUNDABLE_WHEN_COVERED = {
    ProductType.STL: frozenset({S.AWAITING_DELIVERY, S.DELIVERED}),
    ProductType.PHYSICAL: frozenset({S.DELIVERED, S.PICKED_UP, S.RETURNED}),
}


@dataclass(frozen=True)
class LineFact:
    id: UUID
    product_type: ProductType
    status: OrderItemStatus
    line_total_cents: int


@dataclass(frozen=True)
class ItemFact:
    order_item_id: UUID
    amount_cents: int


@dataclass(frozen=True)
class RefundFact:
    id: UUID
    payment_id: UUID
    kind: RefundKind
    status: RefundStatus
    reissued: bool
    amount_cents: int
    items: tuple[ItemFact, ...] = ()


@dataclass(frozen=True)
class ChargebackFact:
    """PR C writes chargebacks; PR B passes none, the rules already count them."""

    payment_id: UUID
    applied_cents: int
    items: tuple[ItemFact, ...] = ()


@dataclass(frozen=True)
class PaymentFact:
    id: UUID
    provider: PaymentProvider
    status: PaymentStatus
    amount_cents: int


@dataclass(frozen=True)
class Ledger:
    """Everything the rules read for one order, after the locks."""

    order_total_cents: int
    lines: tuple[LineFact, ...]
    payment: PaymentFact
    refunds: tuple[RefundFact, ...] = ()
    chargebacks: tuple[ChargebackFact, ...] = ()


def paid_payment(payments: Iterable[PaymentFact]) -> PaymentFact | None:
    """L0: the one payment that reached paid (`uq_payments_one_live` makes it unique)."""
    return next((p for p in payments if p.status in REACHED_PAID), None)


def is_owed(refund: RefundFact) -> bool:
    return (
        refund.kind is not RefundKind.LATE_CAPTURE
        and refund.status is RefundStatus.FAILED
        and not refund.reissued
    )


def is_counted(refund: RefundFact) -> bool:
    """L1: pending, settled, or failed and not reissued (reserved); never voided or late."""
    if refund.kind is RefundKind.LATE_CAPTURE:
        return False
    return refund.status in (RefundStatus.PENDING, RefundStatus.SETTLED) or is_owed(refund)


def _counted_items(ledger: Ledger) -> list[ItemFact]:
    items = [item for r in ledger.refunds if is_counted(r) for item in r.items]
    return items + [item for c in ledger.chargebacks for item in c.items]


def line_balances(ledger: Ledger) -> dict[UUID, int]:
    """L2: the total less counted items; 0 for a `refunded` line or one cancelled bare."""
    covered: dict[UUID, int] = {}
    for item in _counted_items(ledger):
        covered[item.order_item_id] = covered.get(item.order_item_id, 0) + item.amount_cents
    out: dict[UUID, int] = {}
    for line in ledger.lines:
        bare_cancel = line.status is S.CANCELLED and line.id not in covered
        closed = line.status is S.REFUNDED or bare_cancel
        out[line.id] = 0 if closed else line.line_total_cents - covered.get(line.id, 0)
    return out


def payment_balance(ledger: Ledger) -> int:
    """L3: the paid amount less counted refunds and chargeback applied on that payment."""
    pid = ledger.payment.id
    refunded = sum(r.amount_cents for r in ledger.refunds if r.payment_id == pid and is_counted(r))
    charged = sum(c.applied_cents for c in ledger.chargebacks if c.payment_id == pid)
    return ledger.payment.amount_cents - refunded - charged


def check_order_totals(ledger: Ledger) -> None:
    """L7 (Q-2): total = sum of line totals; online, the payment amount equals it too."""
    lines = sum(line.line_total_cents for line in ledger.lines)
    online = ledger.payment.provider is not PaymentProvider.CASH
    if ledger.order_total_cents != lines or (
        online and ledger.payment.amount_cents != ledger.order_total_cents
    ):
        raise OrderTotalMismatchError(
            order_total_cents=ledger.order_total_cents,
            line_total_cents=lines,
            payment_amount_cents=ledger.payment.amount_cents,
        )


def check_request(
    ledger: Ledger, items: Sequence[ItemFact], *, cancelling: Collection[UUID] = ()
) -> None:
    """L4 then L5. Each item within its line's balance and the sum within the payment's;
    an item that empties an unfinished physical line needs VS-031's cancellation."""
    balances = line_balances(ledger)
    available = payment_balance(ledger)
    over_line = any(item.amount_cents > balances[item.order_item_id] for item in items)
    if over_line or sum(item.amount_cents for item in items) > available:
        raise RefundExceedsAvailableError(lines=balances, payment_cents=available)
    by_id = {line.id: line for line in ledger.lines}
    blocked = tuple(
        item.order_item_id
        for item in items
        if by_id[item.order_item_id].status in UNFINISHED_PHYSICAL
        and item.amount_cents == balances[item.order_item_id]
        and item.order_item_id not in cancelling
    )
    if blocked:
        raise RefundRequiresCancellationError(blocked)


def lines_becoming_refunded(ledger: Ledger, items: Sequence[ItemFact]) -> tuple[UUID, ...]:
    """L6: requested lines whose balance reaches 0 in a refundable state; a partial stays."""
    balances = line_balances(ledger)
    by_id = {line.id: line for line in ledger.lines}
    return tuple(
        sorted(
            item.order_item_id
            for item in items
            if balances[item.order_item_id] == item.amount_cents
            and by_id[item.order_item_id].status
            in REFUNDABLE_WHEN_COVERED[by_id[item.order_item_id].product_type]
        )
    )


def refund_facts(ledger: Ledger) -> RefundFacts:
    """L8: the projection's refund inputs from the same rows."""
    return facts_for(ledger.payment, ledger.refunds, ledger.chargebacks)


def facts_for(
    payment: PaymentFact,
    refunds: Iterable[RefundFact],
    chargebacks: Iterable[ChargebackFact] = (),
) -> RefundFacts:
    """L8 without the lines: what a status recompute needs (refund items are not read)."""
    refunds = tuple(refunds)
    live = [
        r
        for r in refunds
        if r.kind is not RefundKind.LATE_CAPTURE
        and r.status in (RefundStatus.PENDING, RefundStatus.SETTLED)
    ]
    applied = [c for c in chargebacks if c.applied_cents > 0]
    covered = sum(r.amount_cents for r in live) + sum(c.applied_cents for c in applied)
    return RefundFacts(
        covers_paid=covered >= payment.amount_cents,
        present=bool(live or applied),
        owed=any(is_owed(r) for r in refunds),
    )


def payment_status(facts: RefundFacts) -> PaymentStatus:
    """The payment projection, with the back edges `refunded -> partially_refunded -> paid`."""
    if facts.covers_paid:
        return PaymentStatus.REFUNDED
    if facts.present or facts.owed:
        return PaymentStatus.PARTIALLY_REFUNDED
    return PaymentStatus.PAID


class RefundAction(StrEnum):
    SETTLE = "settle"
    FAIL = "fail"
    VOID = "void"
    REISSUE = "reissue"


class RefundRefusal(StrEnum):
    NOT_PENDING = "not_pending"
    NOT_FAILED = "not_failed"
    ALREADY_SETTLED = "already_settled"
    ALREADY_REISSUED = "already_reissued"
    LINE_ALREADY_REFUNDED = "line_already_refunded"


@dataclass(frozen=True)
class RefundStep:
    """`target` None with no refusal means an idempotent repeat: 200, nothing written."""

    target: RefundStatus | None = None
    refusal: RefundRefusal | None = None


_NOOP = RefundStep()


def refund_step(
    status: RefundStatus, action: RefundAction, *, reissued: bool, line_refunded: bool = False
) -> RefundStep:
    """U16. Reissue's target is the new refund's status; the old one stays `failed`."""
    if action is RefundAction.SETTLE:
        if status is RefundStatus.SETTLED:
            return _NOOP
        if status is RefundStatus.PENDING:
            return RefundStep(RefundStatus.SETTLED)
        return RefundStep(refusal=RefundRefusal.NOT_PENDING)
    if action is RefundAction.FAIL:
        if status is RefundStatus.FAILED:
            return _NOOP
        if status is RefundStatus.PENDING:
            return RefundStep(RefundStatus.FAILED)
        return RefundStep(refusal=RefundRefusal.NOT_PENDING)
    if action is RefundAction.REISSUE:
        if status is not RefundStatus.FAILED:
            return RefundStep(refusal=RefundRefusal.NOT_FAILED)
        if reissued:
            return RefundStep(refusal=RefundRefusal.ALREADY_REISSUED)
        return RefundStep(RefundStatus.PENDING)
    if status is RefundStatus.VOIDED:
        return _NOOP
    if status is RefundStatus.SETTLED:
        return RefundStep(refusal=RefundRefusal.ALREADY_SETTLED)
    if reissued:
        return RefundStep(refusal=RefundRefusal.ALREADY_REISSUED)
    if line_refunded:
        return RefundStep(refusal=RefundRefusal.LINE_ALREADY_REFUNDED)
    return RefundStep(RefundStatus.VOIDED)
