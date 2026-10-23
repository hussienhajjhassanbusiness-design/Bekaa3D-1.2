"""U13 (VS-030 plan 6.1; owner answers C1, C4): chargeback allocation. Open refunds are
absorbed with their items, so coverage never drops; the admin's items add to it; payout,
refunds still owed plus what the bank took, never exceeds what was paid."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.catalog.application.ports import ProductType
from app.ordering.application.ports import OrderItemStatus, RefundFacts
from app.payments.domain.chargebacks import Allocation, allocate_late, allocate_paid, is_open
from app.payments.domain.enums import PaymentProvider, PaymentStatus, RefundKind, RefundStatus
from app.payments.domain.exceptions import ChargebackAllocationInvalidError
from app.payments.domain.refunds import (
    ChargebackFact,
    ItemFact,
    Ledger,
    LineFact,
    PaymentFact,
    Refund,
    refund_facts,
)

S = OrderItemStatus
PAY = uuid4()


def line(
    status: S = S.DELIVERED, total: int = 5000, kind: ProductType = ProductType.PHYSICAL
) -> LineFact:
    return LineFact(uuid4(), kind, status, total)


def refund(
    *items: tuple[LineFact, int],
    status: RefundStatus = RefundStatus.PENDING,
    kind: RefundKind = RefundKind.ADMIN,
    amount: int | None = None,
    currency: str = "USD",
    reissued: bool = False,
) -> Refund:
    facts = tuple(ItemFact(ln.id, a) for ln, a in items)
    total = amount if amount is not None else sum(i.amount_cents for i in facts)
    return Refund(
        uuid4(),
        uuid4(),
        PAY,
        PaymentProvider.MOCK,
        kind,
        status,
        total,
        currency,
        datetime.now(UTC) if reissued else None,
        facts,
    )


def ledger(*lines: LineFact, refunds: tuple[Refund, ...] = (), paid: int | None = None) -> Ledger:
    total = sum(ln.line_total_cents for ln in lines)
    pay = PaymentFact(PAY, PaymentProvider.MOCK, PaymentStatus.PAID, paid or total, "USD")
    return Ledger(total, lines, pay, tuple(r.fact() for r in refunds))


def after(book: Ledger, allocation: Allocation, remainders: tuple[Refund, ...] = ()) -> RefundFacts:
    voided = set(allocation.voided)
    refunds = tuple(
        replace(r, status=RefundStatus.VOIDED) if r.id in voided else r for r in book.refunds
    )
    return refund_facts(
        Ledger(
            book.order_total_cents,
            book.lines,
            book.payment,
            (*refunds, *(r.fact() for r in remainders)),
            (ChargebackFact(PAY, allocation.applied_cents, allocation.items),),
        )
    )


def test_c1_a_pending_full_refund_on_a_refunded_line_is_absorbed_whole() -> None:
    """The plan's hole: $50 paid, a $50 refund pending (line `refunded`), $50 charged back."""
    a = line(S.REFUNDED)
    full = refund((a, 5000))
    book = ledger(a, refunds=(full,))
    got = allocate_paid(book, [full], charged_cents=5000, items=[])
    assert got.voided == (full.id,) and got.items == (ItemFact(a.id, 5000),)
    assert (got.applied_cents, got.excess_cents, got.remainders) == (5000, 0, ())
    assert after(book, got) == RefundFacts(covers_paid=True, present=True, owed=False)


def test_c1_the_bank_taking_less_leaves_the_rest_owed() -> None:
    a = line(S.REFUNDED)
    full = refund((a, 5000))
    got = allocate_paid(ledger(a, refunds=(full,)), [full], charged_cents=3000, items=[])
    assert got.applied_cents == 3000 and got.excess_cents == 0
    (rest,) = got.remainders
    assert rest.source is full and rest.items == (ItemFact(a.id, 2000),)
    assert rest.amount_cents == 2000


def test_i17_goodwill_absorbed_then_the_admin_allocates_the_rest() -> None:
    """$50 paid, $10 goodwill pending: charged $50 -> voided, applied 50, excess 0."""
    a = line()
    goodwill = refund((a, 1000))
    book = ledger(a, refunds=(goodwill,))
    got = allocate_paid(book, [goodwill], charged_cents=5000, items=[ItemFact(a.id, 4000)])
    assert got.items == (ItemFact(a.id, 5000),) and got.refunded == (a.id,)
    assert (got.applied_cents, got.excess_cents) == (5000, 0)


def test_after_a_settled_full_refund_the_whole_charge_is_excess() -> None:
    a = line(S.REFUNDED)
    settled = refund((a, 5000), status=RefundStatus.SETTLED)
    got = allocate_paid(ledger(a, refunds=(settled,)), [], charged_cents=5000, items=[])
    assert (got.voided, got.applied_cents, got.excess_cents) == ((), 0, 5000)


def test_an_owed_refund_is_absorbed_like_a_pending_one() -> None:
    a = line()
    owed = refund((a, 1000), status=RefundStatus.FAILED)
    assert is_open(owed)
    book = ledger(a, refunds=(owed,))
    got = allocate_paid(book, [owed], charged_cents=1000, items=[])
    assert after(book, got) == RefundFacts(covers_paid=False, present=True, owed=False)


@pytest.mark.parametrize(
    ("state", "moves_to"),
    [
        (S.DELIVERED, "refunded"),
        (S.PICKED_UP, "refunded"),
        (S.RETURNED, "refunded"),
        (S.IN_PRODUCTION, "cancelled"),
        (S.SHIPPED, "cancelled"),
        (S.READY_FOR_PICKUP, "cancelled"),
    ],
)
def test_d4_an_emptied_line_is_refunded_or_cancelled(state: S, moves_to: str) -> None:
    a = line(state)
    got = allocate_paid(ledger(a), [], charged_cents=5000, items=[ItemFact(a.id, 5000)])
    assert (got.refunded, got.cancelled) == (
        ((a.id,), ()) if moves_to == "refunded" else ((), (a.id,))
    )


def test_d4_an_stl_line_awaiting_delivery_is_refunded_and_a_partial_moves_nothing() -> None:
    stl = line(S.AWAITING_DELIVERY, 500, ProductType.STL)
    phys = line(S.IN_PRODUCTION)
    got = allocate_paid(
        ledger(stl, phys),
        [],
        charged_cents=1500,
        items=[ItemFact(stl.id, 500), ItemFact(phys.id, 1000)],
    )
    assert (got.refunded, got.cancelled) == ((stl.id,), ())


@pytest.mark.parametrize(
    "items",
    [
        [(0, 5001)],  # over the line
        [(0, 3000), (1, 3000)],  # over what was charged (5000)
    ],
)
def test_items_over_a_balance_or_the_charge_are_refused(items: list[tuple[int, int]]) -> None:
    a, b = line(), line()
    book = ledger(a, b)
    lines = [a, b]
    with pytest.raises(ChargebackAllocationInvalidError) as refused:
        allocate_paid(
            book,
            [],
            charged_cents=5000,
            items=[ItemFact(lines[i].id, amount) for i, amount in items],
        )
    assert refused.value.chargeable_cents == 5000


def test_items_over_the_payment_balance_are_refused() -> None:
    a = line(total=5000)
    book = ledger(a, paid=3000)  # a cash-like shortfall: the payment caps the lines
    with pytest.raises(ChargebackAllocationInvalidError) as refused:
        allocate_paid(book, [], charged_cents=5000, items=[ItemFact(a.id, 3001)])
    assert refused.value.payment_cents == 3000


def test_a_line_named_twice_is_refused() -> None:
    a = line()
    with pytest.raises(ValueError, match="one item per line"):
        allocate_paid(ledger(a), [], charged_cents=5000, items=[ItemFact(a.id, 1)] * 2)


def test_late_capture_absorbed_with_a_remainder_when_partial() -> None:
    late = refund(kind=RefundKind.LATE_CAPTURE, amount=1200)
    got = allocate_late([late], charged_cents=500)
    assert (got.voided, got.applied_cents, got.excess_cents) == ((late.id,), 500, 0)
    (rest,) = got.remainders
    assert (rest.items, rest.amount_cents) == ((), 700)
    whole = allocate_late([late], charged_cents=1500)
    assert (whole.applied_cents, whole.excess_cents, whole.remainders) == (1200, 300, ())


def test_c4_a_non_usd_late_capture_is_never_compared() -> None:
    late = refund(kind=RefundKind.LATE_CAPTURE, amount=90000, currency="LBP")
    got = allocate_late([late], charged_cents=1000)
    assert (got.voided, got.applied_cents, got.excess_cents, got.remainders) == ((), 0, 1000, ())


def test_absorption_runs_oldest_refund_first_then_by_line() -> None:
    a = LineFact(UUID(int=10), ProductType.PHYSICAL, S.DELIVERED, 5000)
    b = LineFact(UUID(int=11), ProductType.PHYSICAL, S.DELIVERED, 5000)
    first = replace(refund((a, 1000), (b, 1000)), id=UUID(int=1))
    second = replace(refund((a, 500)), id=UUID(int=2))
    got = allocate_paid(
        ledger(a, b, refunds=(first, second)), [second, first], charged_cents=1500, items=[]
    )
    assert got.items == (ItemFact(a.id, 1000), ItemFact(b.id, 500))
    owed = {r.source.id: r.items for r in got.remainders}
    assert owed == {first.id: (ItemFact(b.id, 500),), second.id: (ItemFact(a.id, 500),)}


@settings(database=None, deadline=None, max_examples=300, derandomize=True)
@given(
    amounts=st.lists(st.integers(1, 3000), min_size=0, max_size=3),
    charged=st.integers(1, 10000),
    extra=st.integers(0, 6000),
)
def test_payout_never_exceeds_what_was_paid(amounts: list[int], charged: int, extra: int) -> None:
    a = line(total=10000)
    refunds = tuple(refund((a, x)) for x in amounts if x)
    book = ledger(a, refunds=refunds)
    try:
        got = allocate_paid(
            book,
            list(refunds),
            charged_cents=charged,
            items=[ItemFact(a.id, extra)] if extra else [],
        )
    except ChargebackAllocationInvalidError:
        return
    still_owed = sum(r.amount_cents for r in got.remainders)
    assert got.applied_cents + got.excess_cents == charged
    assert got.applied_cents + still_owed <= book.payment.amount_cents  # invariant M
    covered = sum(i.amount_cents for i in got.items) + still_owed
    assert covered == sum(amounts) + extra  # coverage never drops (C1)
