"""Add/remove a wishlist item (VS-038 plan §3). Each function reports whether
the row's live state actually changed; the caller (the API router) uses that
to decide whether to call `app.catalog.public.adjust_wishlist_count` - this
layer stays free of framework/session concerns (CLAUDE.md, architecture rules).
"""

from uuid import UUID

from app.catalog.application.ports import ProductStore
from app.engagement.application.ports import WishlistStore
from app.engagement.domain.exceptions import WishlistProductUnavailableError


async def add_to_wishlist(
    store: WishlistStore, products: ProductStore, *, user_id: UUID, product_id: UUID
) -> bool:
    """True if a new active row was inserted (caller should increment the
    counter); False if one already existed (no-op, idempotent repeat)."""
    product = await products.get_by_id(product_id)
    if product is None or product.is_deleted or not product.attributes.is_visible:
        raise WishlistProductUnavailableError(product_id)
    return await store.add(user_id=user_id, product_id=product_id)


async def remove_from_wishlist(store: WishlistStore, *, user_id: UUID, product_id: UUID) -> bool:
    """True if an active row was soft-deleted (caller should decrement the
    counter); False if there was none. No visibility check - a customer can
    remove an entry for a product that has since gone non-public (plan §10 Q6).
    """
    return await store.remove(user_id=user_id, product_id=product_id)
