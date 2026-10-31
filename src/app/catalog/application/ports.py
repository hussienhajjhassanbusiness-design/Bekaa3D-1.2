"""Catalog's repository ports. Pure `Protocol`s: the application layer depends
on these, never on `app.catalog.infrastructure` (CLAUDE.md, architecture rules;
BUG-41). `value_admin` declares its own generic `_ValueRepository` port."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.catalog.domain.entities import Category
from app.catalog.domain.enums import AcceptedPaymentMethods as AcceptedPaymentMethods  # VS-049
from app.catalog.domain.enums import ProductType as ProductType  # re-exported (VS-038)
from app.catalog.domain.enums import PurchaseMode as PurchaseMode  # re-exported (VS-036)
from app.catalog.domain.product import Product as Product  # re-exported (VS-038)
from app.catalog.domain.product import ProductDraft
from app.catalog.domain.product_image import ProductImage as ProductImage  # re-exported
from app.catalog.domain.reviewable import ReviewableProduct as ReviewableProduct  # VS-036
from app.catalog.domain.storefront import CartProduct as CartProduct  # re-exported (VS-022)
from app.catalog.domain.storefront import PurchaseRefusal as PurchaseRefusal  # re-exported
from app.catalog.domain.storefront import purchase_refusal as purchase_refusal  # re-exported


class CategoryStore(Protocol):
    async def add(self, *, name: str, slug: str, is_active: bool) -> Category: ...

    async def get_by_id_for_update(self, value_id: UUID) -> Category | None: ...

    async def save(self, value: Category) -> None: ...

    async def is_in_use(self, value_id: UUID) -> bool: ...


class ProductStore(Protocol):
    async def add(self, draft: ProductDraft) -> Product: ...

    async def get_by_id(self, product_id: UUID) -> Product | None: ...

    async def save_if_version(self, product: Product, expected_version: int) -> Product | None:
        """Write and bump `version` only if it is still `expected_version`; else None."""
        ...

    async def current_version(self, product_id: UUID) -> int | None: ...

    async def get_for_update(self, product_id: UUID) -> Product | None:
        """Row-locks the product: image changes serialise on it (docs/product-images.md)."""
        ...

    async def get_many(self, product_ids: list[UUID]) -> list[Product]:
        """One `WHERE id IN (...)` query; no visibility filter (VS-038 plan §3) -
        a caller computing "available" needs a non-public product's own status."""
        ...

    async def top_by_wishlist_count(self, limit: int) -> list[Product]:
        """Highest `wishlist_count` first, id tie-broken; no visibility filter."""
        ...


class ReferenceLocks(Protocol):
    async def lock_live(self, field: str, value_id: UUID) -> bool:
        """Share-lock the value `field` names; False if it is unknown or archived."""
        ...


class ProductImageStore(Protocol):
    async def live_for_product(self, product_id: UUID) -> list[ProductImage]: ...

    async def add(
        self,
        *,
        product_id: UUID,
        storage_key: str,
        alt_text: str | None,
        sort_order: int,
        is_cover: bool,
    ) -> ProductImage: ...

    async def save(self, images: list[ProductImage]) -> None:
        """Write in the given order, so a cover is cleared before another is set."""
        ...


class CartProductReader(Protocol):
    async def get_many(self, product_ids: Sequence[UUID]) -> dict[UUID, CartProduct]:
        """One query; unknown ids are simply absent. No visibility filter: `listed` says it."""
        ...
