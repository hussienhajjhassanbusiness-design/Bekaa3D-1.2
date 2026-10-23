"""U15: the old and new `derive_order_status` over every input (VS-030 plan 3.1a, ADR-042).
The old function is frozen below, verbatim from `order_status.py:35-55` at `326aa40`."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import combinations_with_replacement, product

from app.ordering.domain.enums import OrderItemStatus, OrderStatus, PaymentMethod
from app.ordering.domain.order_status import (
    TERMINAL_LINE_STATES,
    LineState,
    OrderStatusInputs,
    derive_order_status,
)


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
                refunds_cover_paid=self.c,
                refund_present=self.p or self.o,
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


def test_the_frozen_copy_matches_the_function_before_the_reorder() -> None:
    """Removed with the reorder: proves the frozen copy is the shipped VS-023 function."""
    differing = [case for case in every_case() if case.old() is not case.new()]
    assert differing == []


def test_the_classes_are_disjoint() -> None:
    for case in every_case():
        assert sum(predicate(case) for predicate in CLASSES.values()) <= 1, case
