"""The public catalogue's read side (VS-015, docs/storefront-catalogue.md)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.exceptions import ProductValidationError
from app.catalog.domain.product import Product

StorefrontSort = Literal["price", "-price", "-average_rating", "-created_at"]
DEFAULT_SORT: StorefrontSort = "-created_at"
MAX_RATING = Decimal(5)
# `average_rating` is NUMERIC(3,2): a finer bound would be rounded by PostgreSQL.
RATING_STEP = Decimal("0.01")
CursorKey = int | Decimal | datetime

_ONLINE_MODES = frozenset({PurchaseMode.ONLINE_ONLY, PurchaseMode.BOTH})
_WHATSAPP_MODES = frozenset({PurchaseMode.WHATSAPP_ONLY, PurchaseMode.BOTH})


@dataclass(frozen=True)
class StorefrontFilter:
    """The api-endpoints.md 31 allowlist, minus `q` (VS-016). Every facet ANDs."""

    product_type: ProductType | None = None
    category_id: UUID | None = None
    material_id: UUID | None = None
    colour_id: UUID | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    min_rating: Decimal | None = None
    featured: bool | None = None

    def __post_init__(self) -> None:
        errors: dict[str, str] = {}
        low, high = self.price_min_cents, self.price_max_cents
        if low is not None and high is not None and low > high:
            errors["price_min_cents"] = "must not exceed price_max_cents"
        rating = self.min_rating
        if rating is not None and not 0 <= rating <= MAX_RATING:
            errors["min_rating"] = f"must be between 0 and {MAX_RATING}"
        elif rating is not None and rating != rating.quantize(RATING_STEP):
            errors["min_rating"] = "must have at most 2 decimal places"
        if errors:
            raise ProductValidationError(errors)


@dataclass(frozen=True)
class CategoryRef:
    id: UUID
    name: str
    slug: str


@dataclass(frozen=True)
class FacetRef:
    id: UUID
    name: str


@dataclass(frozen=True)
class CommerceCapabilities:
    can_add_to_cart: bool
    can_offer: bool
    whatsapp_available: bool


def capabilities(
    product_type: ProductType, purchase_mode: PurchaseMode | None, is_available: bool
) -> CommerceCapabilities:
    """Product state only; per-customer checks (STL already owned) stay with the cart."""
    physical = product_type is ProductType.PHYSICAL
    return CommerceCapabilities(
        can_add_to_cart=is_available and (not physical or purchase_mode in _ONLINE_MODES),
        can_offer=is_available and not physical,
        whatsapp_available=physical and purchase_mode in _WHATSAPP_MODES,
    )


@dataclass(frozen=True)
class StorefrontProduct:
    """A visible product with the reference names a storefront page shows."""

    product: Product
    category: CategoryRef
    material: FacetRef | None
    colour: FacetRef | None

    @property
    def capabilities(self) -> CommerceCapabilities:
        a = self.product.attributes
        return capabilities(self.product.type, a.purchase_mode, a.is_available)
