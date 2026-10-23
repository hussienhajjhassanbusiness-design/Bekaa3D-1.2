"""U15: the old and new `derive_order_status` over every input (VS-030 plan 3.1a, ADR-042).
The old function is frozen below, verbatim from `order_status.py:35-55` at `326aa40`.
Only D-a and D-c may be reachable; D-b, D-d and D-e must break an invariant."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import combinations_with_replacement, product

import pytest

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import (
    TERMINAL_LINE_STATES,
    LineState,
    OrderStatusInputs,
    RefundFacts,
    derive_order_status,
)

S = OrderItemStatus
ONLINE = PaymentMethod.ONLINE


@dataclass(frozen=True)
class _OldInputs:
    payment_method: PaymentMethod
    cancelled_at_set: bool
    payment_reached_paid: bool
    lines: tuple[LineState, ...]
    refunds_cover_paid: bool = False
    refund_present: bool = False


def derive_order_status_vs023(i: _OldInputs) -> OrderStatus:
    """SRS 20.2 exactly as written (SRS.md:1172-1186); a reorder is VS-030's decision."""
    states = [line.status for line in i.lines]
    all_cancelled = bool(states) and all(s is OrderItemStatus.CANCELLED for s in states)
    if not i.payment_reached_paid:
        if i.payment_method is PaymentMethod.ONLINE:
            return OrderStatus.CANCELLED if i.cancelled_at_set else OrderStatus.PENDING_PAYMENT
        return OrderStatus.CANCELLED if all_cancelled else OrderStatus.IN_PROGRESS
    if all_cancelled:
        return OrderStatus.CANCELLED
    if i.refunds_cover_paid:
        return OrderStatus.REFUNDED
    if states and all(s is OrderItemStatus.REFUNDED for s in states):
        return OrderStatus.REFUNDED
    if i.refund_present:
        return OrderStatus.PARTIALLY_REFUNDED
    if states and all(s in TERMINAL_LINE_STATES for s in states):
        return OrderStatus.COMPLETED
    return OrderStatus.IN_PROGRESS


@dataclass(frozen=True)
class Case:
    method: PaymentMethod
    cancelled_at_set: bool
    paid: bool
    states: tuple[OrderItemStatus, ...]
    c: bool  # refunds cover the paid money
    p: bool  # a pending or settled refund is present
    o: bool  # a failed refund is owed

    def old(self) -> OrderStatus:
        return derive_order_status_vs023(
            _OldInputs(
                self.method,
                self.cancelled_at_set,
                self.paid,
                tuple(LineState(s) for s in self.states),
                refunds_cover_paid=self.c,
                refund_present=self.p or self.o,
            )
        )

    def new(self) -> OrderStatus:
        return derive_order_status(
            OrderStatusInputs(
                self.method,
                self.cancelled_at_set,
                self.paid,
                tuple(LineState(s) for s in self.states),
                refunds=RefundFacts(covers_paid=self.c, present=self.p, owed=self.o),
            )
        )


def every_case() -> Iterator[Case]:
    multisets = [
        combo
        for size in (1, 2, 3)
        for combo in combinations_with_replacement(list(OrderItemStatus), size)
    ]
    for method, cancelled, paid, states, (c, p, o) in product(
        list(PaymentMethod),
        (False, True),
        (False, True),
        multisets,
        product((False, True), repeat=3),
    ):
        yield Case(method, cancelled, paid, states, c, p, o)


def _all(case: Case, status: OrderItemStatus) -> bool:
    return all(s is status for s in case.states)


def consistent(case: Case) -> bool:
    """I1: o => not c. I2: every line refunded and not o => c. I3: a refunded line => p or o."""
    i1 = not (case.o and case.c)
    i2 = not (_all(case, OrderItemStatus.REFUNDED) and not case.o) or case.c
    i3 = OrderItemStatus.REFUNDED not in case.states or case.p or case.o
    return i1 and i2 and i3


def _paid_not_ac(case: Case) -> bool:
    return case.paid and not _all(case, OrderItemStatus.CANCELLED)


CLASSES: dict[str, Callable[[Case], bool]] = {
    "D-a": lambda k: k.paid and k.o and _all(k, OrderItemStatus.CANCELLED),
    "D-b": lambda k: _paid_not_ac(k) and k.o and k.c,
    "D-c": lambda k: _paid_not_ac(k) and k.o and not k.c and _all(k, OrderItemStatus.REFUNDED),
    "D-d": lambda k: (
        _paid_not_ac(k) and not k.o and not k.c and _all(k, OrderItemStatus.REFUNDED) and k.p
    ),
    "D-e": lambda k: (
        _paid_not_ac(k) and not k.o and not k.c and _all(k, OrderItemStatus.REFUNDED) and not k.p
    ),
}


def test_the_domain_is_every_combination() -> None:
    assert sum(1 for _ in every_case()) == 23_232


def test_the_classes_are_disjoint() -> None:
    for case in every_case():
        assert sum(predicate(case) for predicate in CLASSES.values()) <= 1, case


INTENDED = {"D-a", "D-c"}  # PR #8 cases B and A; the rest are unreachable (I1-I3)


def _class_of(case: Case) -> str | None:
    return next((name for name, predicate in CLASSES.items() if predicate(case)), None)


def test_old_and_new_differ_exactly_on_the_five_classes() -> None:
    counts = dict.fromkeys(CLASSES, 0)
    for case in every_case():
        differs = case.old() is not case.new()
        name = _class_of(case)
        assert differs is (name is not None), (case, case.old(), case.new())
        if name is not None:
            counts[name] += 1
            assert case.new() is OrderStatus.PARTIALLY_REFUNDED or name == "D-e", case
    print("U15 per-class counts:", counts)  # for the PR description
    assert all(counts.values()), counts


def test_only_the_intended_differences_are_reachable() -> None:
    """D-b, D-d, D-e never consistent; D-c always; D-a exactly when not covered (I1)."""
    reachable = dict.fromkeys(CLASSES, 0)
    for case in every_case():
        name = _class_of(case)
        if name is None:
            continue
        expected = name == "D-c" or (name == "D-a" and not case.c)
        assert consistent(case) is expected, (name, case)
        reachable[name] += consistent(case)
    assert {name for name, n in reachable.items() if n} == INTENDED, reachable


@pytest.mark.parametrize(
    ("label", "case", "old", "new", "can_happen"),
    [
        (
            "PR #8 case A (D-c): full refund failed, owed",
            Case(ONLINE, False, True, (S.REFUNDED,), c=False, p=False, o=True),
            OrderStatus.REFUNDED,
            OrderStatus.PARTIALLY_REFUNDED,
            True,
        ),
        (
            "PR #8 case B (D-a): every line cancelled, cancellation refund failed",
            Case(ONLINE, False, True, (S.CANCELLED, S.CANCELLED), c=False, p=False, o=True),
            OrderStatus.CANCELLED,
            OrderStatus.PARTIALLY_REFUNDED,
            True,
        ),
        (
            # Cannot happen (I2, I3): a refunded line exists only through a refund that
            # covers it. This was test_order_status's old "paid-all-lines-refunded" input.
            "cannot happen (D-e): every line refunded, no refund facts at all",
            Case(ONLINE, False, True, (S.REFUNDED,), c=False, p=False, o=False),
            OrderStatus.REFUNDED,
            OrderStatus.COMPLETED,
            False,
        ),
        (
            "after the reissue: case A covered again",
            Case(ONLINE, False, True, (S.REFUNDED,), c=True, p=True, o=False),
            OrderStatus.REFUNDED,
            OrderStatus.REFUNDED,
            True,
        ),
        (
            "after the reissue: case B cancelled again",
            Case(ONLINE, False, True, (S.CANCELLED, S.CANCELLED), c=True, p=True, o=False),
            OrderStatus.CANCELLED,
            OrderStatus.CANCELLED,
            True,
        ),
    ],
)
def test_named_rows(
    label: str, case: Case, old: OrderStatus, new: OrderStatus, can_happen: bool
) -> None:
    assert (case.old(), case.new(), consistent(case)) == (old, new, can_happen), label
