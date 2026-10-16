"""Catalog's published surface for other bounded contexts.

Another context may import from here or from `app.catalog.application.ports`,
and from nowhere else in Catalog (enforced by
`tests/unit/test_deep_architecture.py`).
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import ProductStore
from app.catalog.infrastructure.models import ProductModel
from app.catalog.infrastructure.product_repository import ProductRepository

__all__ = ["adjust_wishlist_count", "product_store"]


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


async def product_store(session: AsyncSession = Depends(get_session)) -> ProductStore:
    """A `ProductStore` bound to the request's session, for a FastAPI route in
    another context to depend on - the same shape `identity.public.current_user`
    already uses to hand out Identity's own session-bound state."""
    return ProductRepository(session)
