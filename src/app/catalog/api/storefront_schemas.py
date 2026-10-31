"""Public product payloads (api-endpoints.md 30). Fields are an allowlist: nothing
administrative (visibility, version, wishlist count, weight) is ever exposed."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel

from app.catalog.api.product_image_schemas import media_url
from app.catalog.api.product_schemas import DimensionsRead, PriceRead
from app.catalog.domain.enums import AcceptedPaymentMethods, ProductType, PurchaseMode
from app.catalog.domain.product_image import ProductImage
from app.catalog.domain.storefront import FacetRef, StorefrontProduct


class PublicImage(BaseModel):
    id: UUID
    url: str
    alt_text: str | None
    is_cover: bool

    @classmethod
    def from_entity(cls, image: ProductImage, media_base_url: str) -> Self:
        return cls(
            id=image.id,
            url=media_url(media_base_url, image.storage_key),
            alt_text=image.alt_text,
            is_cover=image.is_cover,
        )


class CategorySummary(BaseModel):
    id: UUID
    name: str
    slug: str


class FacetSummary(BaseModel):
    id: UUID
    name: str


def _facet(value: FacetRef | None) -> FacetSummary | None:
    return FacetSummary(id=value.id, name=value.name) if value else None


class ProductListItem(BaseModel):
    id: UUID
    type: ProductType
    name: str
    slug: str
    cover_image: PublicImage | None
    price: PriceRead
    category: CategorySummary
    material: FacetSummary | None
    colour: FacetSummary | None
    is_available: bool
    purchase_mode: PurchaseMode | None
    accepted_payment_methods: AcceptedPaymentMethods | None
    average_rating: float
    review_count: int
    is_featured: bool

    @classmethod
    def _fields(
        cls, item: StorefrontProduct, images: list[ProductImage], media_base_url: str
    ) -> dict[str, object]:
        p, a = item.product, item.product.attributes
        cover = next((i for i in images if i.is_cover), None)
        return {
            "id": p.id,
            "type": p.type,
            "name": a.name,
            "slug": a.slug,
            "cover_image": PublicImage.from_entity(cover, media_base_url) if cover else None,
            "price": PriceRead(amount_cents=a.price_cents, currency=a.currency),
            "category": CategorySummary(
                id=item.category.id, name=item.category.name, slug=item.category.slug
            ),
            "material": _facet(item.material),
            "colour": _facet(item.colour),
            "is_available": a.is_available,
            "purchase_mode": a.purchase_mode,
            "accepted_payment_methods": a.accepted_payment_methods,
            "average_rating": float(p.average_rating),
            "review_count": p.review_count,
            "is_featured": a.is_featured,
        }

    @classmethod
    def from_storefront(
        cls, item: StorefrontProduct, images: list[ProductImage], media_base_url: str
    ) -> Self:
        return cls.model_validate(cls._fields(item, images, media_base_url))


class Capabilities(BaseModel):
    """Product-level only; the cart still checks per-customer rules such as STL ownership."""

    can_add_to_cart: bool
    can_offer: bool
    whatsapp_available: bool


class ProductDetail(ProductListItem):
    description: str | None
    images: list[PublicImage]
    seo_title: str | None
    seo_description: str | None
    og_image_url: str | None
    dimensions: DimensionsRead | None
    production_lead_time_days: int | None
    batch_size: int | None
    max_quantity_per_line: int | None
    capabilities: Capabilities

    @classmethod
    def from_storefront(
        cls, item: StorefrontProduct, images: list[ProductImage], media_base_url: str
    ) -> Self:
        a, derived = item.product.attributes, item.capabilities
        return cls.model_validate(
            cls._fields(item, images, media_base_url)
            | {
                "description": a.description,
                "images": [PublicImage.from_entity(i, media_base_url) for i in images],
                "seo_title": a.seo_title,
                "seo_description": a.seo_description,
                "og_image_url": a.og_image_url,
                "dimensions": DimensionsRead(**a.dimensions.as_dict()) if a.dimensions else None,
                "production_lead_time_days": a.production_lead_time_days,
                "batch_size": a.batch_size,
                "max_quantity_per_line": a.max_quantity_per_line,
                "capabilities": Capabilities(
                    can_add_to_cart=derived.can_add_to_cart,
                    can_offer=derived.can_offer,
                    whatsapp_available=derived.whatsapp_available,
                ),
            }
        )


class ProductPage(BaseModel):
    items: list[ProductListItem]
    next_cursor: str | None
