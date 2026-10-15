"""Catalog's published surface for other bounded contexts.

Another context may import from here or from `app.catalog.application.ports`,
and from nowhere else in Catalog (enforced by
`tests/unit/test_deep_architecture.py`). Keep this module to writes only - a
cross-context read goes through `application.ports.ProductStore` instead
(VS-038 plan §3); grow this file rather than reaching around it.
"""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.models import ProductModel

__all__ = ["adjust_wishlist_count"]


async def adjust_wishlist_count(session: AsyncSession, product_id: UUID, delta: int) -> None:
    """`delta` is +1 or -1, from a caller that already confirmed a real state
    change. Runs in the caller's transaction and does not commit - same shape
    as `app.engagement.public.create_notification`.

    No visibility filter: a decrement must land even if the product went
    non-public between add and remove (VS-038 plan §3/§10 Q6).
    """
    await session.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .values(wishlist_count=ProductModel.wishlist_count + delta)
    )
