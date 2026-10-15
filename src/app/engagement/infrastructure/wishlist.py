from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.public import adjust_wishlist_count


class SqlWishlistCounter:
    """Adapts `app.catalog.public.adjust_wishlist_count` to `WishlistCounter`,
    bound to the same session as the `WishlistStore` adapter it is paired
    with. Deliberately does not commit - the caller's request-scoped unit of
    work does (see `app.engagement.public.create_notification`'s callers)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def adjust(self, product_id: UUID, delta: int) -> None:
        await adjust_wishlist_count(self._session, product_id, delta)
