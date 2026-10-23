"""Receipt confirmation and problem reports (VS-029b; SRS 8.8, BR-147, ADR-041). Pure.
Physical lines only: an STL "delivered" means the file was emailed, not received."""

from collections.abc import Iterable
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus
from app.ordering.domain.exceptions import NoDeliveredLineError
from app.ordering.domain.orders import OrderLine

RECEIVED_STATES = frozenset({OrderItemStatus.DELIVERED, OrderItemStatus.PICKED_UP})


def received_line_ids(lines: Iterable[OrderLine]) -> list[UUID]:
    """The physical lines the customer has in hand, by id; none is a 409 for both actions."""
    ids = sorted(
        line.id
        for line in lines
        if line.product_type is ProductType.PHYSICAL and line.fulfillment_status in RECEIVED_STATES
    )
    if not ids:
        raise NoDeliveredLineError()
    return ids
