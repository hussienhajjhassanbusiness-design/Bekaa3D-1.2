from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.catalog.domain.enums import AcceptedPaymentMethods, ProductType, PurchaseMode
from app.catalog.domain.exceptions import ArchivedValueNotMutableError, ProductValidationError

ENTITY_TYPE = "Product"
CURRENCY = "USD"

# SRS 6.1: blank on an STL product (6.2), and checked by `ck_products_type_integrity`.
PHYSICAL_ONLY_FIELDS = (
    "purchase_mode",
    "accepted_payment_methods",
    "material_id",
    "colour_id",
    "dimensions",
    "production_lead_time_days",
    "batch_size",
    "max_quantity_per_line",
    "weight_grams",
)
PHYSICAL_REQUIRED_FIELDS = (
    "purchase_mode",
    "accepted_payment_methods",
    "production_lead_time_days",
    "batch_size",
    "max_quantity_per_line",
)
REFERENCE_FIELDS = ("category_id", "material_id", "colour_id")


@dataclass(frozen=True)
class Dimensions:
    length_mm: int
    width_mm: int
    height_mm: int

    def __post_init__(self) -> None:
        for name in ("length_mm", "width_mm", "height_mm"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ProductValidationError({f"dimensions.{name}": "must be a positive integer"})

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ProductAttributes:
    """Everything an administrator may set. `type` is not here: it is immutable."""

    category_id: UUID
    name: str
    slug: str
    price_cents: int
    currency: str = CURRENCY
    description: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    og_image_url: str | None = None
    is_visible: bool = False
    is_featured: bool = False
    is_available: bool = True
    purchase_mode: PurchaseMode | None = None
    accepted_payment_methods: AcceptedPaymentMethods | None = None
    material_id: UUID | None = None
    colour_id: UUID | None = None
    dimensions: Dimensions | None = None
    production_lead_time_days: int | None = None
    batch_size: int | None = None
    max_quantity_per_line: int | None = None
    weight_grams: int | None = None

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, UUID | PurchaseMode | AcceptedPaymentMethods):
                value = str(value)
            elif isinstance(value, Dimensions):
                value = value.as_dict()
            out[f.name] = value
        return out


EDITABLE_FIELDS = frozenset(f.name for f in fields(ProductAttributes))


def with_create_defaults(product_type: ProductType, attrs: ProductAttributes) -> ProductAttributes:
    """BR-019: a physical product created without accepted methods accepts both."""
    if product_type is ProductType.PHYSICAL and attrs.accepted_payment_methods is None:
        return replace(attrs, accepted_payment_methods=AcceptedPaymentMethods.ONLINE_OR_CASH)
    return attrs


def check_product(product_type: ProductType, attrs: ProductAttributes) -> None:
    """Every field rule at once, so the caller can report them together."""
    errors: dict[str, str] = {}
    if not attrs.name.strip():
        errors["name"] = "must not be blank"
    if attrs.price_cents < 0:
        errors["price"] = "amount_cents must be zero or more"
    if attrs.currency != CURRENCY:
        errors["price"] = f"currency must be {CURRENCY}"
    if product_type is ProductType.PHYSICAL:
        for name in PHYSICAL_REQUIRED_FIELDS:
            if getattr(attrs, name) is None:
                errors[name] = "is required on a physical product"
        _check_bound(errors, "production_lead_time_days", attrs.production_lead_time_days, 0)
        _check_bound(errors, "batch_size", attrs.batch_size, 1)
        _check_bound(errors, "max_quantity_per_line", attrs.max_quantity_per_line, 1)
        _check_bound(errors, "weight_grams", attrs.weight_grams, 1)
    else:
        for name in PHYSICAL_ONLY_FIELDS:
            if getattr(attrs, name) is not None:
                errors[name] = "is not allowed on an STL product"
    if errors:
        raise ProductValidationError(errors)


def _check_bound(errors: dict[str, str], name: str, value: int | None, minimum: int) -> None:
    if value is not None and value < minimum:
        errors[name] = f"must be at least {minimum}"


@dataclass(frozen=True)
class ProductDraft:
    """A product not yet stored. Building one is what validates it."""

    type: ProductType
    attributes: ProductAttributes

    def __post_init__(self) -> None:
        check_product(self.type, self.attributes)


@dataclass
class Product:
    id: UUID
    type: ProductType
    attributes: ProductAttributes
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    average_rating: Decimal = field(default=Decimal(0))
    review_count: int = 0
    wishlist_count: int = 0

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def ensure_live(self) -> None:
        if self.is_deleted:
            raise ArchivedValueNotMutableError(ENTITY_TYPE, self.id)

    def apply_update(self, changes: dict[str, Any], at: datetime) -> bool:
        """Merge `changes`, then validate the merged whole. Returns whether anything moved."""
        self.ensure_live()
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"not editable: {sorted(unknown)}")
        merged = replace(self.attributes, **changes)
        if merged == self.attributes:
            return False
        check_product(self.type, merged)
        self.attributes = merged
        self.updated_at = at
        return True

    def delete(self, at: datetime) -> None:
        """Soft delete. Visibility is left alone: deletion is a separate concept."""
        self.ensure_live()
        self.deleted_at = at
        self.updated_at = at

    def audit_snapshot(self) -> dict[str, Any]:
        """Editable state plus version; aggregates are left out (ADR-020)."""
        return {
            "type": str(self.type),
            **self.attributes.snapshot(),
            "version": self.version,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }
