"""ADR-043 (VS-031 must-resolve 2): a cancel refunds each paid line's whole remaining
balance, so the line balances still sum to the payment's and a chargeback for the whole
payment can always be allocated afterwards."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.catalog.application.ports import ProductType
from app.ordering.application.ports import OrderItemStatus
from app.payments.domain.chargebacks import allocate_paid
from app.payments.domain.enums import PaymentProvider, PaymentStatus, RefundKind, RefundStatus
from app.payments.domain.refunds import (
    UNFINISHED_PHYSICAL,
    ItemFact,
    Ledger,
    LineFact,
    PaymentFact,
    RefundFact,
    cancellation_items,
    check_request,
    line_balances,
    payment_balance,
)

S = OrderItemStatus
PAY = uuid4()
UNFINISHED = sorted(UNFINISHED_PHYSICAL - {S.SHIPPED})  # what a paid cancel can take


def _refund(items: tuple[ItemFact, ...], kind: RefundKind = RefundKind.ADMIN) -> RefundFact:
    amount = sum(i.amount_cents for i in items)
    return RefundFact(uuid4(), PAY, kind, RefundStatus.PENDING, False, amount, items)


def _cancel(book: Ledger, cancelling: frozenset[UUID]) -> Ledger:
    items = cancellation_items(book, cancelling, line_balances(book))
    check_request(book, items, cancelling=cancelling)
    lines = tuple(
        replace(ln, status=S.CANCELLED) if ln.id in cancelling else ln for ln in book.lines
    )
    refunds = (*book.refunds, _refund(items, RefundKind.CANCELLATION)) if items else book.refunds
    return replace(book, lines=lines, refunds=refunds)


@settings(max_examples=300, deadline=None)
@given(
    data=st.data(),
    count=st.integers(min_value=1, max_value=4),
    with_stl=st.booleans(),
)
def test_after_any_cancel_balances_agree_and_a_full_chargeback_allocates(
    data: st.DataObject, count: int, with_stl: bool
) -> None:
    lines = [
        LineFact(
            uuid4(),
            ProductType.PHYSICAL,
            data.draw(st.sampled_from(UNFINISHED)),
            data.draw(st.integers(min_value=0, max_value=5000)),
        )
        for _ in range(count)
    ]
    if with_stl:
        lines.append(LineFact(uuid4(), ProductType.STL, S.DELIVERED, 2000))
    goodwill = tuple(
        ItemFact(ln.id, data.draw(st.integers(min_value=1, max_value=ln.line_total_cents - 1)))
        for ln in lines
        if ln.line_total_cents > 1 and data.draw(st.booleans())
    )
    total = sum(ln.line_total_cents for ln in lines)
    pay = PaymentFact(PAY, PaymentProvider.MOCK, PaymentStatus.PAID, total, "USD")
    book = Ledger(total, tuple(lines), pay, (_refund(goodwill),) if goodwill else ())
    physical = [ln.id for ln in lines if ln.product_type is ProductType.PHYSICAL]
    picked = data.draw(st.lists(st.sampled_from(physical), min_size=1, unique=True))
    cancelled = _cancel(book, frozenset(picked))

    balances = line_balances(cancelled)
    assert sum(balances.values()) == payment_balance(cancelled)
    assert all(balances[i] == 0 for i in picked)
    remaining = [ItemFact(i, b) for i, b in balances.items() if b > 0]
    allocation = allocate_paid(cancelled, (), charged_cents=total, items=remaining)
    assert allocation.excess_cents == total - payment_balance(cancelled)


def test_a_zero_balance_line_gets_no_item() -> None:
    zero = LineFact(uuid4(), ProductType.PHYSICAL, S.PENDING, 0)
    paid = LineFact(uuid4(), ProductType.PHYSICAL, S.IN_PRODUCTION, 900)
    pay = PaymentFact(PAY, PaymentProvider.MOCK, PaymentStatus.PAID, 900, "USD")
    book = Ledger(900, (zero, paid), pay)
    items = cancellation_items(book, {zero.id, paid.id}, line_balances(book))
    assert items == (ItemFact(paid.id, 900),)


@pytest.mark.parametrize("status", [S.DELIVERED, S.RETURNED, S.CANCELLED, S.REFUNDED])
def test_only_an_unfinished_line_is_cancelled_with_a_refund(status: S) -> None:
    done = LineFact(uuid4(), ProductType.PHYSICAL, status, 900)
    pay = PaymentFact(PAY, PaymentProvider.MOCK, PaymentStatus.PAID, 900, "USD")
    book = Ledger(900, (done,), pay)
    with pytest.raises(ValueError, match="unfinished"):
        cancellation_items(book, {done.id}, line_balances(book))
