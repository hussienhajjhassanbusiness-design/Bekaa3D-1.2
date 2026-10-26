from dataclasses import dataclass
from uuid import UUID

from app.catalog.domain.enums import PurchaseMode


@dataclass(frozen=True)
class ReviewableProduct:
    """What reviews need of a product (VS-036 plan 3.4). `visible` is the storefront's
    rule (SRS 6.5); `purchase_mode` drives the D14 badge mask, None for STL."""

    id: UUID
    slug: str
    live: bool
    visible: bool
    purchase_mode: PurchaseMode | None
