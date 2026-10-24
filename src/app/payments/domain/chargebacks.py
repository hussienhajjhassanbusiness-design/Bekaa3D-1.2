"""Chargeback allocation (VS-030 plan 3.3; ADR-042 d3-d4; owner answers C1, C4). Pure: the
rows were read after the orders lock. Open refunds are absorbed with their own items, so no
line's coverage changes; the admin's items add coverage on top."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.payments.domain.enums import PaymentProvider, RefundStatus
from app.payments.domain.exceptions import ChargebackAllocationInvalidError
from app.payments.domain.refunds import (
    REFUNDABLE_WHEN_COVERED,
    UNFINISHED_PHYSICAL,
    ItemFact,
    Ledger,
    Refund,
    line_balances,
    payment_balance,
)

USD = "USD"


@dataclass(frozen=True)
class Remainder:
    """What a voided refund still owes after the bank's charge: a new pending refund."""

    source: Refund
    items: tuple[ItemFact, ...]
    amount_cents: int


@dataclass(frozen=True)
class Allocation:
    voided: tuple[UUID, ...]
    items: tuple[ItemFact, ...]  # the chargeback's items: absorbed first, then the admin's
    applied_cents: int
    excess_cents: int
    remainders: tuple[Remainder, ...]
    refunded: tuple[UUID, ...] = ()
    cancelled: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class NewChargeback:
    """Its id is chosen first, so the refunds it absorbs can name it (rank 4 before 5)."""

    id: UUID
    order_id: UUID
    payment_id: UUID
    provider: PaymentProvider
    dispute_reference: str
    charged_cents: int
    applied_cents: int
    excess_cents: int
    reason: str
    recorded_by: UUID
    received_at: datetime
    items: tuple[ItemFact, ...]


def is_open(refund: Refund) -> bool:
    """Still to be paid out: pending, or failed and not reissued (owed)."""
    if refund.status is RefundStatus.PENDING:
        return True
    return refund.status is RefundStatus.FAILED and refund.reissued_at is None


def _absorb(
    open_refunds: Sequence[Refund], charged_cents: int
) -> tuple[dict[UUID, int], int, tuple[Remainder, ...]]:
    """C1: in (refund id, line id) order, up to what was charged; the rest is a remainder."""
    budget, total, absorbed = charged_cents, 0, dict[UUID, int]()
    remainders: list[Remainder] = []
    for refund in sorted(open_refunds, key=lambda r: r.id):
        left: list[ItemFact] = []
        if refund.items:
            for item in sorted(refund.items, key=lambda i: str(i.order_item_id)):
                take = min(item.amount_cents, budget)
                budget, total = budget - take, total + take
                if take:
                    absorbed[item.order_item_id] = absorbed.get(item.order_item_id, 0) + take
                if item.amount_cents > take:
                    left.append(ItemFact(item.order_item_id, item.amount_cents - take))
            owed = sum(item.amount_cents for item in left)
        else:  # a late-capture refund has no lines
            take = min(refund.amount_cents, budget)
            budget, total, owed = budget - take, total + take, refund.amount_cents - take
        if owed:
            remainders.append(Remainder(refund, tuple(left), owed))
    return absorbed, total, tuple(remainders)


def allocate_paid(
    ledger: Ledger,
    open_refunds: Sequence[Refund],
    *,
    charged_cents: int,
    items: Sequence[ItemFact],
) -> Allocation:
    """A paid payment: absorb its open refunds, then the admin's items, which must cover
    exactly the charge left or, if less, all that is still refundable: excess exists only
    once nothing is. An emptied line is `refunded` (delivered, STL) or `cancelled` (D4)."""
    if len({item.order_item_id for item in items}) != len(items):
        raise ValueError("one item per line")
    absorbed, absorbed_cents, remainders = _absorb(open_refunds, charged_cents)
    balances, available = line_balances(ledger), payment_balance(ledger)
    required = min(charged_cents - absorbed_cents, available)
    added = sum(item.amount_cents for item in items)
    if added != required or any(item.amount_cents > balances[item.order_item_id] for item in items):
        raise ChargebackAllocationInvalidError(
            lines=balances, payment_cents=available, chargeable_cents=required
        )
    by_id = {line.id: line for line in ledger.lines}
    emptied = [by_id[i.order_item_id] for i in items if i.amount_cents == balances[i.order_item_id]]
    refunded = sorted(
        line.id for line in emptied if line.status in REFUNDABLE_WHEN_COVERED[line.product_type]
    )
    cancelled = sorted(line.id for line in emptied if line.status in UNFINISHED_PHYSICAL)
    merged = dict(absorbed)
    for item in items:
        merged[item.order_item_id] = merged.get(item.order_item_id, 0) + item.amount_cents
    return Allocation(
        voided=tuple(sorted(r.id for r in open_refunds)),
        items=tuple(ItemFact(i, a) for i, a in sorted(merged.items(), key=lambda p: str(p[0]))),
        applied_cents=absorbed_cents + added,
        excess_cents=charged_cents - absorbed_cents - added,
        remainders=remainders,
        refunded=tuple(refunded),
        cancelled=tuple(cancelled),
    )


def allocate_late(open_refunds: Sequence[Refund], *, charged_cents: int) -> Allocation:
    """A late-captured attempt (no lines): absorb its open `late_capture` refund, leaving a
    remainder if the bank took less. One not in USD cannot be compared: all excess (C4)."""
    if any(r.currency != USD for r in open_refunds):
        return Allocation((), (), 0, charged_cents, ())
    _, absorbed_cents, remainders = _absorb(open_refunds, charged_cents)
    return Allocation(
        voided=tuple(sorted(r.id for r in open_refunds)),
        items=(),
        applied_cents=absorbed_cents,
        excess_cents=charged_cents - absorbed_cents,
        remainders=remainders,
    )
