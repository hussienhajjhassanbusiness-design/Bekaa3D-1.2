from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import ProductType

# VS-022 plan Q7: bounds the response, the Catalog batch and checkout's line loop.
MAX_CART_LINES = 50


@dataclass(frozen=True)
class Cart:
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CartLine:
    """One product in a cart. `price_snapshot_cents` is display-only: checkout charges
    the live price and uses this only to detect a change (VS-022 plan §3.6)."""

    id: UUID
    cart_id: UUID
    product_id: UUID
    product_type: ProductType
    quantity: int
    price_snapshot_cents: int
    currency: str
    created_at: datetime
    updated_at: datetime
