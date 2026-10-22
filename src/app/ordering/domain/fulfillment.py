"""Fulfillment rules (VS-028 plan 3.1; SRS 7.4): the matrix over the kept lines, and the
dispatch estimate. Pure."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import FulfillmentMethod, PaymentMethod
from app.ordering.domain.exceptions import InvalidFulfillmentError, PaymentMethodNotAllowedError
from app.ordering.domain.orders import NewOrderLine

DELIVERY_FEE_NOTE = "The delivery fee is paid to the courier on delivery."


@dataclass(frozen=True)
class Fulfillment:
    method: FulfillmentMethod | None
    address_id: UUID | None
    contact_phone: str | None


def resolve_fulfillment(
    product_types: Sequence[ProductType],
    *,
    payment_method: PaymentMethod,
    method: FulfillmentMethod | None,
    address_id: UUID | None,
    contact_phone: str | None,
) -> Fulfillment:
    """SRS 7.4 over the kept lines; cash needs every one of them physical (ADR-024 d2)."""
    physical = any(t is ProductType.PHYSICAL for t in product_types)
    if not physical:
        if method is not None or address_id is not None or contact_phone is not None:
            raise InvalidFulfillmentError("An STL-only order has no fulfillment.")
        fulfillment = Fulfillment(None, None, None)
    elif method is FulfillmentMethod.DELIVERY:
        if address_id is None or contact_phone is not None:
            raise InvalidFulfillmentError("Delivery takes an address and no contact phone.")
        fulfillment = Fulfillment(method, address_id, None)
    elif method is FulfillmentMethod.PICKUP:
        if address_id is not None or contact_phone is None:
            raise InvalidFulfillmentError("Pickup takes a contact phone and no address.")
        fulfillment = Fulfillment(method, None, contact_phone)
    else:
        raise InvalidFulfillmentError("A physical order needs delivery or pickup.")
    if payment_method is PaymentMethod.CASH and not all(
        t is ProductType.PHYSICAL for t in product_types
    ):
        raise PaymentMethodNotAllowedError("cash_requires_physical")
    return fulfillment


def dispatch_days(lines: Sequence[NewOrderLine]) -> int | None:
    """BR-037: the longest of lead x ceil(quantity / batch) over physical lines."""
    days = [
        line.lead_time_days_snapshot * -(-line.quantity // line.batch_size_snapshot)
        for line in lines
        if line.product_type is ProductType.PHYSICAL
        and line.lead_time_days_snapshot is not None
        and line.batch_size_snapshot is not None
    ]
    return max(days) if days else None


def estimated_dispatch_at(placed_at: datetime, days: int | None) -> datetime | None:
    return None if days is None else placed_at + timedelta(days=days)
