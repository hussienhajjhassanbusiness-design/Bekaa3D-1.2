"""Add/remove a wishlist item (VS-038 plan §3). The counter only ever moves
when `store.add`/`remove` reports a real state change, via the framework-free
`WishlistCounter` port - never by the service re-deriving before/after state.
"""

from uuid import UUID

from app.catalog.application.ports import ProductStore
from app.engagement.application.ports import WishlistCounter, WishlistStore
from app.engagement.domain.exceptions import WishlistProductUnavailableError


async def add_to_wishlist(
    store: WishlistStore,
    products: ProductStore,
    counter: WishlistCounter,
    *,
    user_id: UUID,
    product_id: UUID,
) -> bool:
    """True if a new active row was inserted; False on an idempotent repeat."""
    product = await products.get_by_id(product_id)
    if product is None or product.is_deleted or not product.attributes.is_visible:
        raise WishlistProductUnavailableError(product_id)
    changed = await store.add(user_id=user_id, product_id=product_id)
    if changed:
        await counter.adjust(product_id, 1)
    return changed


async def remove_from_wishlist(
    store: WishlistStore, counter: WishlistCounter, *, user_id: UUID, product_id: UUID
) -> bool:
    """True if an active row was soft-deleted; False if there was none. No
    visibility check - a customer can remove an entry for a product that has
    since gone non-public (plan §10 Q6)."""
    changed = await store.remove(user_id=user_id, product_id=product_id)
    if changed:
        await counter.adjust(product_id, -1)
    return changed


async def erase_wishlist(store: WishlistStore, counter: WishlistCounter, *, user_id: UUID) -> int:
    """VS-045: every counter moves down once, products in id order so two deletions never
    deadlock on them."""
    product_ids = sorted(await store.remove_all(user_id), key=lambda p: p.bytes)
    for product_id in product_ids:
        await counter.adjust(product_id, -1)
    return len(product_ids)
