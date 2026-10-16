"""Admin wishlist analytics (VS-038, api-endpoints.md 14.2/admin analytics table).
No `from`/`to`: neither the SRS nor api-endpoints.md defines a date range for a
wishlist total, and `wishlist_count` has no time dimension to filter by - so the
bound this route declares, per the "bounded by explicit date ranges/limits" rule,
is `limit` alone."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import ProductStore
from app.catalog.public import product_store
from app.engagement.api.schemas import WishlistAnalytics, WishlistAnalyticsItem
from app.engagement.infrastructure.wishlist import SqlWishlistRepository
from app.identity.public import AdminBoundaryRoute

admin_router = APIRouter(prefix="/analytics", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Caller is not an administrator."},
    422: {"description": "`limit` above the maximum."},
}


@admin_router.get(
    "/wishlist",
    response_model=WishlistAnalytics,
    summary="Wishlist totals and most-wishlisted products",
    responses=_RESPONSES,
)
async def wishlist_analytics(
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
    products: ProductStore = Depends(product_store),
) -> WishlistAnalytics:
    """Totals and most-wishlisted both include non-public products:
    `wishlist_count` tracks total interest, not current storefront
    eligibility (plan §10 Q6)."""
    total_active = await SqlWishlistRepository(session).count_active()
    top = await products.top_by_wishlist_count(limit)
    return WishlistAnalytics(
        total_active=total_active,
        most_wishlisted=[
            WishlistAnalyticsItem(
                product_id=product.id,
                name=product.attributes.name,
                slug=product.attributes.slug,
                wishlist_count=product.wishlist_count,
            )
            for product in top
        ],
    )
