"""Which payment methods the kept lines accept (BR-019, BR-141, ADR-048). Pure."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.catalog.application.ports import AcceptedPaymentMethods, ProductType
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    NoCommonPaymentMethodError,
    PaymentMethodNotAllowedError,
)

ALL_METHODS: Final = frozenset(PaymentMethod)
_METHODS: Final = {
    AcceptedPaymentMethods.ONLINE: frozenset({PaymentMethod.ONLINE}),
    AcceptedPaymentMethods.CASH: frozenset({PaymentMethod.CASH}),
    AcceptedPaymentMethods.ONLINE_OR_CASH: ALL_METHODS,
}


@dataclass(frozen=True)
class LineMethods:
    product_id: UUID
    product_type: ProductType
    accepted: AcceptedPaymentMethods | None


def accepted_methods(
    product_type: ProductType, accepted: AcceptedPaymentMethods | None
) -> frozenset[PaymentMethod]:
    """An STL accepts online only: an emailed file cannot be taken back (ADR-024 d2)."""
    if product_type is ProductType.STL:
        return frozenset({PaymentMethod.ONLINE})
    if accepted is None:  # ck_products_type_integrity forbids it
        raise ValueError("A physical product always has accepted payment methods.")
    return _METHODS[accepted]


def shared_methods(sets: Iterable[frozenset[PaymentMethod]]) -> frozenset[PaymentMethod]:
    shared = ALL_METHODS
    for methods in sets:
        shared &= methods
    return shared


def in_order(methods: frozenset[PaymentMethod]) -> list[PaymentMethod]:
    return [m for m in PaymentMethod if m in methods]


def require_accepted(lines: Sequence[LineMethods], chosen: PaymentMethod) -> None:
    """No shared method refuses whatever was chosen; else every line must accept `chosen`."""
    accepted = {
        line.product_id: accepted_methods(line.product_type, line.accepted) for line in lines
    }
    if not shared_methods(accepted.values()):
        raise NoCommonPaymentMethodError(
            [(product_id, in_order(methods)) for product_id, methods in accepted.items()]
        )
    if chosen is PaymentMethod.CASH and any(line.product_type is ProductType.STL for line in lines):
        raise PaymentMethodNotAllowedError("cash_requires_physical")
    refusing = tuple(product_id for product_id, m in accepted.items() if chosen not in m)
    if refusing:
        raise PaymentMethodNotAllowedError(f"{chosen.value}_not_accepted", refusing)
