"""The refund rules L0-L8 and the state machine (VS-030 plan 3.2, 6.1 U3 and U6-U10, U16)."""

from itertools import product
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.catalog.application.ports import ProductType
from app.ordering.application.ports import OrderItemStatus, RefundFacts
from app.payments.domain.enums import PaymentProvider, PaymentStatus, RefundKind, RefundStatus
from app.payments.domain.exceptions import (
    OrderTotalMismatchError,
    RefundExceedsAvailableError,
    RefundRequiresCancellationError,
)
from app.payments.domain.refunds import (
    UNFINISHED_PHYSICAL,
    ChargebackFact,
    ItemFact,
    Ledger,
    LineFact,
    PaymentFact,
    RefundAction,
    RefundFact,
    RefundRefusal,
    check_order_totals,
    check_request,
    is_counted,
    line_balances,
    lines_becoming_refunded,
    paid_payment,
    payment_balance,
    payment_status,
    refund_facts,
    refund_step,
)

S = OrderItemStatus
STL, PHYSICAL = ProductType.STL, ProductType.PHYSICAL
PAY_ID = uuid4()


def line(status: S = S.DELIVERED, total: int = 1000, kind: ProductType = PHYSICAL) -> LineFact:
    return LineFact(uuid4(), kind, status, total)


def payment(amount: int, provider: PaymentProvider = PaymentProvider.MOCK) -> PaymentFact:
    return PaymentFact(PAY_ID, provider, PaymentStatus.PAID, amount)


def refund(
    *items: tuple[LineFact, int],
    status: RefundStatus = RefundStatus.PENDING,
    reissued: bool = False,
    kind: RefundKind = RefundKind.ADMIN,
) -> RefundFact:
    facts = tuple(ItemFact(ln.id, amount) for ln, amount in items)
    total = sum(item.amount_cents for item in facts)
    return RefundFact(uuid4(), PAY_ID, kind, status, reissued, total, facts)


def ledger(
    *lines: LineFact,
    refunds: tuple[RefundFact, ...] = (),
    chargebacks: tuple[ChargebackFact, ...] = (),
    pay: PaymentFact | None = None,
) -> Ledger:
    total = sum(ln.line_total_cents for ln in lines)
    return Ledger(total, lines, pay or payment(total), refunds, chargebacks)


def item(ln: LineFact, amount: int) -> ItemFact:
    return ItemFact(ln.id, amount)


# --- L0 ---------------------------------------------------------------------------------


def test_only_a_payment_that_reached_paid_is_the_paid_one() -> None:
    def fact(status: PaymentStatus) -> PaymentFact:
        return PaymentFact(uuid4(), PaymentProvider.MOCK, status, 100)

    failed, paid = fact(PaymentStatus.FAILED), fact(PaymentStatus.PARTIALLY_REFUNDED)
    assert paid_payment([failed, paid]) is paid
    assert paid_payment([failed, fact(PaymentStatus.PENDING), fact(PaymentStatus.EXPIRED)]) is None


# --- U6: L1-L3 --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "reissued", "counted"),
    [
        (RefundStatus.PENDING, False, True),
        (RefundStatus.SETTLED, False, True),
        (RefundStatus.FAILED, False, True),  # reserved: still owed
        (RefundStatus.FAILED, True, False),  # its reissue counts instead
        (RefundStatus.VOIDED, False, False),
    ],
)
def test_which_refunds_count_against_the_balances(
    status: RefundStatus, reissued: bool, counted: bool
) -> None:
    a = line()
    r = refund((a, 300), status=status, reissued=reissued)
    book = ledger(a, refunds=(r,))
    assert is_counted(r) is counted
    assert line_balances(book)[a.id] == (700 if counted else 1000)
    assert payment_balance(book) == (700 if counted else 1000)


def test_a_late_capture_refund_never_counts() -> None:
    a = line()
    late = RefundFact(uuid4(), PAY_ID, RefundKind.LATE_CAPTURE, RefundStatus.PENDING, False, 400)
    book = ledger(a, refunds=(late,))
    assert not is_counted(late)
    assert (line_balances(book)[a.id], payment_balance(book)) == (1000, 1000)
    assert refund_facts(book) == RefundFacts()


def test_a_bare_cancelled_line_and_a_refunded_line_have_no_balance() -> None:
    cancelled, refunded_line, live = line(S.CANCELLED), line(S.REFUNDED), line(S.DELIVERED)
    balances = line_balances(ledger(cancelled, refunded_line, live))
    assert balances == {cancelled.id: 0, refunded_line.id: 0, live.id: 1000}


def test_chargeback_items_and_applied_count() -> None:
    a = line()
    cb = ChargebackFact(PAY_ID, 250, (item(a, 250),))
    book = ledger(a, chargebacks=(cb,))
    assert (line_balances(book)[a.id], payment_balance(book)) == (750, 750)
    assert refund_facts(book) == RefundFacts(covers_paid=False, present=True, owed=False)


def test_a_cancelled_line_with_refund_items_keeps_its_remaining_balance() -> None:
    a = line(S.CANCELLED)
    book = ledger(a, refunds=(refund((a, 400)),))
    assert line_balances(book)[a.id] == 600


# --- U7: L4 and L5 ----------------------------------------------------------------------


def test_exactly_the_balance_passes_and_one_cent_more_is_refused() -> None:
    a = line(S.DELIVERED)
    book = ledger(a, refunds=(refund((a, 400)),))
    check_request(book, [item(a, 600)])
    with pytest.raises(RefundExceedsAvailableError) as refused:
        check_request(book, [item(a, 601)])
    assert refused.value.lines == {a.id: 600} and refused.value.payment_cents == 600


def test_the_payment_balance_caps_the_sum_even_when_each_line_fits() -> None:
    a, b = line(), line()
    # A cash order whose payment recorded less than the lines (a cancelled-then-paid mix).
    book = ledger(a, b, pay=payment(1500, PaymentProvider.CASH))
    check_request(book, [item(a, 1000), item(b, 500)])
    with pytest.raises(RefundExceedsAvailableError):
        check_request(book, [item(a, 1000), item(b, 501)])


@pytest.mark.parametrize("state", sorted(UNFINISHED_PHYSICAL))
def test_emptying_an_unfinished_physical_line_needs_a_cancellation(state: S) -> None:
    a = line(state)
    book = ledger(a)
    with pytest.raises(RefundRequiresCancellationError) as refused:
        check_request(book, [item(a, 1000)])
    assert refused.value.order_item_ids == (a.id,)
    check_request(book, [item(a, 999)])
    check_request(book, [item(a, 1000)], cancelling={a.id})


def test_an_unfinished_line_emptied_by_its_last_cents_also_needs_a_cancellation() -> None:
    a = line(S.SHIPPED)
    book = ledger(a, refunds=(refund((a, 900)),))
    with pytest.raises(RefundRequiresCancellationError):
        check_request(book, [item(a, 100)])


def test_an_awaiting_delivery_stl_line_may_be_refunded_in_full() -> None:
    a = line(S.AWAITING_DELIVERY, kind=STL)
    check_request(ledger(a), [item(a, 1000)])


def test_a_closed_line_has_nothing_to_refund() -> None:
    for state in (S.REFUNDED, S.CANCELLED):
        a, b = line(state), line()
        with pytest.raises(RefundExceedsAvailableError):
            check_request(ledger(a, b), [item(a, 1)])


# --- U8: L6 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "state", "becomes_refunded"),
    [
        (STL, S.AWAITING_DELIVERY, True),
        (STL, S.DELIVERED, True),
        (PHYSICAL, S.DELIVERED, True),
        (PHYSICAL, S.PICKED_UP, True),
        (PHYSICAL, S.RETURNED, True),
        *[(PHYSICAL, s, False) for s in sorted(UNFINISHED_PHYSICAL)],
    ],
)
def test_which_covered_lines_become_refunded(
    kind: ProductType, state: S, becomes_refunded: bool
) -> None:
    a = line(state, kind=kind)
    covered = lines_becoming_refunded(ledger(a), [item(a, 1000)])
    assert covered == ((a.id,) if becomes_refunded else ())


def test_a_partial_refund_leaves_the_line_in_its_state() -> None:
    a = line(S.DELIVERED)
    assert lines_becoming_refunded(ledger(a), [item(a, 999)]) == ()


def test_the_last_cents_of_a_line_make_it_refunded() -> None:
    a = line(S.DELIVERED)
    book = ledger(a, refunds=(refund((a, 999)),))
    assert lines_becoming_refunded(book, [item(a, 1)]) == (a.id,)


def test_an_owed_failed_refund_reserves_the_line_so_it_is_not_refunded_twice() -> None:
    a = line(S.DELIVERED)
    book = ledger(a, refunds=(refund((a, 500), status=RefundStatus.FAILED),))
    assert lines_becoming_refunded(book, [item(a, 500)]) == (a.id,)
    with pytest.raises(RefundExceedsAvailableError):
        check_request(book, [item(a, 501)])


# --- U9: L7 (Q-2) -----------------------------------------------------------------------


def test_the_order_total_must_equal_its_lines() -> None:
    a = line()
    book = ledger(a)
    check_order_totals(book)
    with pytest.raises(OrderTotalMismatchError) as refused:
        check_order_totals(Ledger(1001, (a,), book.payment))
    assert (refused.value.order_total_cents, refused.value.line_total_cents) == (1001, 1000)


def test_a_cash_order_total_must_equal_its_lines_too() -> None:
    a = line()
    cash = payment(1000, PaymentProvider.CASH)
    with pytest.raises(OrderTotalMismatchError):
        check_order_totals(Ledger(999, (a,), cash))


def test_an_online_payment_must_equal_the_order_total_and_cash_need_not() -> None:
    a, b = line(), line(S.CANCELLED)
    with pytest.raises(OrderTotalMismatchError):
        check_order_totals(ledger(a, b, pay=payment(1000)))
    check_order_totals(ledger(a, b, pay=payment(1000, PaymentProvider.CASH)))


# --- L8 and U3 --------------------------------------------------------------------------


def test_refund_facts_from_rows() -> None:
    a, b = line(), line()
    full = refund((a, 1000), (b, 1000), status=RefundStatus.SETTLED)
    failed = refund((a, 1000), status=RefundStatus.FAILED)
    reissue = refund((a, 1000))
    voided = refund((a, 1000), status=RefundStatus.VOIDED)
    assert refund_facts(ledger(a, b, refunds=(full,))) == RefundFacts(True, True, False)
    assert refund_facts(ledger(a, b, refunds=(failed,))) == RefundFacts(False, False, True)
    reissued = refund((a, 1000), status=RefundStatus.FAILED, reissued=True)
    assert refund_facts(ledger(a, b, refunds=(reissued, reissue))) == RefundFacts(
        False, True, False
    )
    assert refund_facts(ledger(a, b, refunds=(voided,))) == RefundFacts()


@pytest.mark.parametrize(("covers", "present", "owed"), list(product((False, True), repeat=3)))
def test_the_payment_projection(covers: bool, present: bool, owed: bool) -> None:
    expected = (
        PaymentStatus.REFUNDED
        if covers
        else PaymentStatus.PARTIALLY_REFUNDED
        if present or owed
        else PaymentStatus.PAID
    )
    assert payment_status(RefundFacts(covers, present, owed)) is expected


def test_the_payment_projection_goes_back_after_a_void() -> None:
    a = line()
    pending = refund((a, 1000))
    book = ledger(a, refunds=(pending,))
    assert payment_status(refund_facts(book)) is PaymentStatus.REFUNDED
    voided = refund((a, 1000), status=RefundStatus.VOIDED)
    assert payment_status(refund_facts(ledger(a, refunds=(voided,)))) is PaymentStatus.PAID
    partial = (refund((a, 400)), voided)
    assert payment_status(refund_facts(ledger(a, refunds=partial))) is (
        PaymentStatus.PARTIALLY_REFUNDED
    )


# --- U10: random request sequences against one ledger ------------------------------------

_STATES = [S.DELIVERED, S.PICKED_UP, S.RETURNED, S.SHIPPED, S.AWAITING_DELIVERY]


@settings(database=None, deadline=None, max_examples=300, derandomize=True)
@given(
    totals=st.lists(st.integers(1, 5000), min_size=1, max_size=4),
    states=st.lists(st.sampled_from(_STATES), min_size=4, max_size=4),
    steps=st.lists(
        st.tuples(
            st.lists(st.tuples(st.integers(0, 3), st.integers(1, 6000)), min_size=1, max_size=3),
            st.sampled_from(["pending", "settle", "fail", "fail_reissue", "void"]),
        ),
        max_size=12,
    ),
)
def test_no_sequence_of_refunds_pays_out_more_than_was_paid(
    totals: list[int], states: list[S], steps: list[tuple[list[tuple[int, int]], str]]
) -> None:
    lines = [
        LineFact(
            uuid4(),
            STL if states[i] is S.AWAITING_DELIVERY else PHYSICAL,
            states[i],
            total,
        )
        for i, total in enumerate(totals)
    ]
    refunds: list[RefundFact] = []

    def book() -> Ledger:
        return ledger(*lines, refunds=tuple(refunds))

    for picks, outcome in steps:
        merged: dict[UUID, int] = {}
        for index, amount in picks:
            target = lines[index % len(lines)].id
            merged[target] = merged.get(target, 0) + amount
        items = [ItemFact(i, a) for i, a in merged.items()]
        try:
            check_request(book(), items, cancelling={ln.id for ln in lines})
        except RefundExceedsAvailableError:
            continue
        done = set(lines_becoming_refunded(book(), items))
        lines = [
            LineFact(ln.id, ln.product_type, S.REFUNDED, ln.line_total_cents)
            if ln.id in done
            else ln
            for ln in lines
        ]
        status = {
            "pending": RefundStatus.PENDING,
            "settle": RefundStatus.SETTLED,
            "fail": RefundStatus.FAILED,
            "fail_reissue": RefundStatus.FAILED,
            "void": RefundStatus.VOIDED,
        }[outcome]
        if outcome == "void" and done:
            status = RefundStatus.PENDING  # a refund that refunded a line cannot be voided
        new = RefundFact(
            uuid4(),
            PAY_ID,
            RefundKind.ADMIN,
            status,
            outcome == "fail_reissue",
            sum(i.amount_cents for i in items),
            tuple(items),
        )
        refunds.append(new)
        if outcome == "fail_reissue":
            refunds.append(
                RefundFact(
                    uuid4(),
                    PAY_ID,
                    RefundKind.ADMIN,
                    RefundStatus.PENDING,
                    False,
                    new.amount_cents,
                    new.items,
                )
            )
        current = book()
        counted = [r for r in current.refunds if is_counted(r)]
        assert sum(r.amount_cents for r in counted) <= current.payment.amount_cents
        for ln in current.lines:
            covered = sum(
                i.amount_cents for r in counted for i in r.items if i.order_item_id == ln.id
            )
            assert covered <= ln.line_total_cents
        facts = refund_facts(current)
        if all(ln.status is S.REFUNDED for ln in current.lines) and not facts.owed:
            assert facts.covers_paid
        assert not (facts.owed and facts.covers_paid)  # invariant I1


# --- U16: the refund state machine -------------------------------------------------------

R = RefundStatus
STEP_TABLE = {
    # (status, reissued, line_refunded, action): (target, refusal)
    (R.PENDING, False, False, RefundAction.SETTLE): (R.SETTLED, None),
    (R.SETTLED, False, False, RefundAction.SETTLE): (None, None),
    (R.FAILED, False, False, RefundAction.SETTLE): (None, RefundRefusal.NOT_PENDING),
    (R.FAILED, True, False, RefundAction.SETTLE): (None, RefundRefusal.NOT_PENDING),
    (R.VOIDED, False, False, RefundAction.SETTLE): (None, RefundRefusal.NOT_PENDING),
    (R.PENDING, False, False, RefundAction.FAIL): (R.FAILED, None),
    (R.FAILED, False, False, RefundAction.FAIL): (None, None),
    (R.FAILED, True, False, RefundAction.FAIL): (None, None),
    (R.SETTLED, False, False, RefundAction.FAIL): (None, RefundRefusal.NOT_PENDING),
    (R.VOIDED, False, False, RefundAction.FAIL): (None, RefundRefusal.NOT_PENDING),
    (R.PENDING, False, False, RefundAction.VOID): (R.VOIDED, None),
    (R.FAILED, False, False, RefundAction.VOID): (R.VOIDED, None),
    (R.VOIDED, False, False, RefundAction.VOID): (None, None),
    (R.SETTLED, False, False, RefundAction.VOID): (None, RefundRefusal.ALREADY_SETTLED),
    (R.FAILED, True, False, RefundAction.VOID): (None, RefundRefusal.ALREADY_REISSUED),
    (R.PENDING, False, True, RefundAction.VOID): (None, RefundRefusal.LINE_ALREADY_REFUNDED),
    (R.FAILED, False, True, RefundAction.VOID): (None, RefundRefusal.LINE_ALREADY_REFUNDED),
    (R.SETTLED, False, True, RefundAction.VOID): (None, RefundRefusal.ALREADY_SETTLED),
    (R.VOIDED, False, True, RefundAction.VOID): (None, None),
    (R.FAILED, False, False, RefundAction.REISSUE): (R.PENDING, None),
    (R.FAILED, True, False, RefundAction.REISSUE): (None, RefundRefusal.ALREADY_REISSUED),
    (R.PENDING, False, False, RefundAction.REISSUE): (None, RefundRefusal.NOT_FAILED),
    (R.SETTLED, False, False, RefundAction.REISSUE): (None, RefundRefusal.NOT_FAILED),
    (R.VOIDED, False, False, RefundAction.REISSUE): (None, RefundRefusal.NOT_FAILED),
}


@pytest.mark.parametrize(("key", "expected"), list(STEP_TABLE.items()), ids=str)
def test_each_refund_step(
    key: tuple[R, bool, bool, RefundAction], expected: tuple[R | None, RefundRefusal | None]
) -> None:
    status, reissued, line_refunded, action = key
    step = refund_step(status, action, reissued=reissued, line_refunded=line_refunded)
    assert (step.target, step.refusal) == expected


def test_settled_and_voided_are_terminal() -> None:
    for status, action in product((R.SETTLED, R.VOIDED), RefundAction):
        step = refund_step(status, action, reissued=False)
        assert step.target is None, (status, action)


def test_a_voided_refund_is_never_reissued() -> None:
    for reissued, line_refunded in product((False, True), repeat=2):
        step = refund_step(
            R.VOIDED, RefundAction.REISSUE, reissued=reissued, line_refunded=line_refunded
        )
        assert step.refusal is RefundRefusal.NOT_FAILED
