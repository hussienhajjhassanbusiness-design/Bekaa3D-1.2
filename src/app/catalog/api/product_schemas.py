from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from app.catalog.api.product_image_schemas import ProductImageRead
from app.catalog.api.schemas import MAX_NAME_LENGTH, ReferenceName
from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.product import Dimensions, Product, ProductAttributes
from app.catalog.domain.product_image import ProductImage
from app.core.text import (
    CONTROL_CHARACTER_MESSAGE,
    has_control_characters,
    reject_control_characters,
)

# Edge limits (docs/products.md): the columns are TEXT/INTEGER/BIGINT, so these keep
# an oversized value a 422 rather than a database error.
MAX_DESCRIPTION_LENGTH = 10_000
MAX_SEO_DESCRIPTION_LENGTH = 500
MAX_URL_LENGTH = 2_000
PG_INT_MAX = 2_147_483_647
PG_BIGINT_MAX = 9_223_372_036_854_775_807


def _reject_controls_keep_line_breaks(value: str) -> str:
    if has_control_characters(value, allow_line_breaks=True):
        raise ValueError(CONTROL_CHARACTER_MESSAGE)
    return value


Description = Annotated[
    str,
    Field(max_length=MAX_DESCRIPTION_LENGTH),
    AfterValidator(_reject_controls_keep_line_breaks),
]
SeoTitle = Annotated[
    str, Field(max_length=MAX_NAME_LENGTH), AfterValidator(reject_control_characters)
]
SeoDescription = Annotated[
    str, Field(max_length=MAX_SEO_DESCRIPTION_LENGTH), AfterValidator(reject_control_characters)
]
HttpUrlText = Annotated[str, Field(max_length=MAX_URL_LENGTH, pattern=r"^https?://\S+$")]
Slug = Annotated[str, Field(min_length=1, max_length=MAX_NAME_LENGTH)]
LeadTimeDays = Annotated[StrictInt, Field(ge=0, le=PG_INT_MAX)]
PositiveInt = Annotated[StrictInt, Field(gt=0, le=PG_INT_MAX)]


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_cents: Annotated[StrictInt, Field(ge=0, le=PG_BIGINT_MAX)]
    currency: Literal["USD"] = "USD"


class DimensionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_mm: PositiveInt
    width_mm: PositiveInt
    height_mm: PositiveInt

    def to_domain(self) -> Dimensions:
        return Dimensions(self.length_mm, self.width_mm, self.height_mm)


class _ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Description | None = None
    seo_title: SeoTitle | None = None
    seo_description: SeoDescription | None = None
    og_image_url: HttpUrlText | None = None
    purchase_mode: PurchaseMode | None = None
    material_id: UUID | None = None
    colour_id: UUID | None = None
    dimensions: DimensionsIn | None = None
    production_lead_time_days: LeadTimeDays | None = None
    batch_size: PositiveInt | None = None
    max_quantity_per_line: PositiveInt | None = None
    weight_grams: PositiveInt | None = None

    def _domain_values(self, names: set[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name in names:
            value = getattr(self, name)
            if name == "price":
                out["price_cents"], out["currency"] = value.amount_cents, value.currency
            elif name == "dimensions":
                out["dimensions"] = value.to_domain() if value is not None else None
            else:
                out[name] = value
        return out


class AdminProductCreate(_ProductFields):
    """api-endpoints.md 29.10. `type` and price are required; aggregates are not accepted."""

    type: ProductType
    category_id: UUID
    name: ReferenceName
    slug: Slug
    price: PriceIn
    is_visible: StrictBool = False
    is_featured: StrictBool = False
    is_available: StrictBool = True

    def to_attributes(self) -> ProductAttributes:
        return ProductAttributes(**self._domain_values(set(type(self).model_fields) - {"type"}))


# Fields a PATCH may set but never to null.
_NOT_NULLABLE = {
    "category_id",
    "name",
    "slug",
    "price",
    "is_visible",
    "is_featured",
    "is_available",
}


class AdminProductUpdate(_ProductFields):
    """Every field optional except `version`; `type` and aggregates are refused (extra=forbid)."""

    version: Annotated[StrictInt, Field(ge=1, le=PG_INT_MAX)]
    category_id: UUID | None = None
    name: ReferenceName | None = None
    slug: Slug | None = None
    price: PriceIn | None = None
    is_visible: StrictBool | None = None
    is_featured: StrictBool | None = None
    is_available: StrictBool | None = None

    @model_validator(mode="after")
    def _sensible_patch(self) -> Self:
        if not self.model_fields_set - {"version"}:
            raise ValueError("at least one field besides version must be provided")
        nulled = sorted(
            n for n in _NOT_NULLABLE & self.model_fields_set if getattr(self, n) is None
        )
        if nulled:
            raise ValueError(f"these fields cannot be null: {', '.join(nulled)}")
        return self

    def changes(self) -> dict[str, Any]:
        return self._domain_values(self.model_fields_set - {"version"})


class PriceRead(BaseModel):
    amount_cents: int
    currency: str


class DimensionsRead(BaseModel):
    length_mm: int
    width_mm: int
    height_mm: int


class AdminProductDetail(BaseModel):
    id: UUID
    type: ProductType
    category_id: UUID
    name: str
    description: str | None
    slug: str
    seo_title: str | None
    seo_description: str | None
    og_image_url: str | None
    price: PriceRead
    is_visible: bool
    is_featured: bool
    is_available: bool
    purchase_mode: PurchaseMode | None
    material_id: UUID | None
    colour_id: UUID | None
    dimensions: DimensionsRead | None
    production_lead_time_days: int | None
    batch_size: int | None
    max_quantity_per_line: int | None
    weight_grams: int | None
    average_rating: float
    review_count: int
    wishlist_count: int
    version: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    images: list[ProductImageRead]

    @classmethod
    def from_entity(cls, product: Product, images: list[ProductImage], media_base_url: str) -> Self:
        """`images` are the live ones, in display order (api-endpoints.md 15.1)."""
        a = product.attributes
        plain = {
            n: getattr(a, n)
            for n in a.snapshot()
            if n not in {"price_cents", "currency", "dimensions"}
        }
        return cls(
            **plain,
            id=product.id,
            type=product.type,
            price=PriceRead(amount_cents=a.price_cents, currency=a.currency),
            dimensions=DimensionsRead(**a.dimensions.as_dict()) if a.dimensions else None,
            average_rating=float(product.average_rating),
            review_count=product.review_count,
            wishlist_count=product.wishlist_count,
            version=product.version,
            deleted_at=product.deleted_at,
            created_at=product.created_at,
            updated_at=product.updated_at,
            images=[ProductImageRead.from_entity(i, media_base_url) for i in images],
        )


class AdminProductPage(BaseModel):
    items: list[AdminProductDetail]
    next_cursor: str | None
