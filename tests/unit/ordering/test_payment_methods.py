"""Accepted payment methods over the kept lines (VS-049; BR-019, BR-141, ADR-048)."""

from itertools import combinations_with_replacement
from uuid import uuid4

import pytest

from app.catalog.application.ports import AcceptedPaymentMethods, ProductType
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    NoCommonPaymentMethodError,
    PaymentMethodNotAllowedError,
)
from app.ordering.domain.payment_methods import (
    LineMethods,
    accepted_methods,
    require_accepted,
    shared_methods,
)

ONLINE, CASH = PaymentMethod.ONLINE, PaymentMethod.CASH
A = AcceptedPaymentMethods
SETS = {A.ONLINE: {ONLINE}, A.CASH: {CASH}, A.ONLINE_OR_CASH: {ONLINE, CASH}}


def physical(accepted: AcceptedPaymentMethods) -> LineMethods:
    return LineMethods(uuid4(), ProductType.PHYSICAL, accepted)


def stl() -> LineMethods:
    return LineMethods(uuid4(), ProductType.STL, None)


@pytest.mark.parametrize("accepted", list(A))
def test_each_value_maps_to_its_methods(accepted: AcceptedPaymentMethods) -> None:
    assert accepted_methods(ProductType.PHYSICAL, accepted) == SETS[accepted]


@pytest.mark.parametrize("accepted", [None, *A])
def test_an_stl_accepts_online_only_whatever_is_stored(
    accepted: AcceptedPaymentMethods | None,
) -> None:
    assert accepted_methods(ProductType.STL, accepted) == {ONLINE}


def test_a_physical_product_without_a_value_is_a_bug_not_a_default() -> None:
    with pytest.raises(ValueError):
        accepted_methods(ProductType.PHYSICAL, None)


def test_no_lines_share_every_method() -> None:
    assert shared_methods([]) == {ONLINE, CASH}


@pytest.mark.parametrize("with_stl", [False, True])
@pytest.mark.parametrize("values", list(combinations_with_replacement(list(A), 2)))
@pytest.mark.parametrize("chosen", [ONLINE, CASH])
def test_every_combination_refuses_or_passes_as_the_rule_says(
    values: tuple[AcceptedPaymentMethods, ...], with_stl: bool, chosen: PaymentMethod
) -> None:
    lines = [physical(v) for v in values] + ([stl()] if with_stl else [])
    shared = set.intersection(*(SETS[v] for v in values), *([{ONLINE}] if with_stl else []))
    if not shared:
        with pytest.raises(NoCommonPaymentMethodError) as none:
            require_accepted(lines, chosen)
        assert [p for p, _ in none.value.lines] == [line.product_id for line in lines]
    elif chosen not in shared:
        with pytest.raises(PaymentMethodNotAllowedError):
            require_accepted(lines, chosen)
    else:
        require_accepted(lines, chosen)


def test_no_shared_method_lists_each_lines_methods_in_enum_order() -> None:
    cash_only, online_only, file = physical(A.CASH), physical(A.ONLINE), stl()
    with pytest.raises(NoCommonPaymentMethodError) as caught:
        require_accepted([cash_only, online_only, file], ONLINE)
    assert caught.value.lines == [
        (cash_only.product_id, [CASH]),
        (online_only.product_id, [ONLINE]),
        (file.product_id, [ONLINE]),
    ]


def test_an_stl_beside_a_cash_only_product_has_no_shared_method_even_when_cash_is_chosen() -> None:
    with pytest.raises(NoCommonPaymentMethodError):
        require_accepted([stl(), physical(A.CASH)], CASH)


def test_cash_with_an_stl_line_keeps_its_reason() -> None:
    with pytest.raises(PaymentMethodNotAllowedError) as caught:
        require_accepted([stl(), physical(A.ONLINE_OR_CASH)], CASH)
    assert (caught.value.reason, caught.value.product_ids) == ("cash_requires_physical", ())


@pytest.mark.parametrize(
    ("refusing", "chosen", "reason"),
    [(A.ONLINE, CASH, "cash_not_accepted"), (A.CASH, ONLINE, "online_not_accepted")],
)
def test_a_method_one_product_refuses_names_only_that_product(
    refusing: AcceptedPaymentMethods, chosen: PaymentMethod, reason: str
) -> None:
    both, other = physical(A.ONLINE_OR_CASH), physical(refusing)
    with pytest.raises(PaymentMethodNotAllowedError) as caught:
        require_accepted([both, other], chosen)
    assert (caught.value.reason, caught.value.product_ids) == (reason, (other.product_id,))
