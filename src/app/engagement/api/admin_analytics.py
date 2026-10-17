"""Admin engagement analytics: wishlist (VS-038; bounded by `limit` alone, as a wishlist
total has no time dimension) and the Bring Your Idea funnel (VS-035)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import ProductStore
from app.catalog.public import product_store
from app.engagement.api.custom_request_schemas import CustomRequestFunnelAnalytics
from app.engagement.api.queue_cursor import check_range, invalid_query
from app.engagement.api.schemas import WishlistAnalytics, WishlistAnalyticsItem
from app.engagement.domain.custom_request import QUOTE_CURRENCY
from app.engagement.infrastructure.custom_requests import SqlCustomRequestPipelineRepository
from app.engagement.infrastructure.wishlist import SqlWishlistRepository
from app.identity.public import AdminBoundaryRoute

admin_router = APIRouter(prefix="/analytics", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_DEFAULT_FUNNEL_SPAN = timedelta(days=90)
_MAX_FUNNEL_SPAN = timedelta(days=366)

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


@admin_router.get(
    "/custom-requests/funnel",
    response_model=CustomRequestFunnelAnalytics,
    summary="Bring Your Idea conversion funnel by submission date",
    responses={
        401: {"description": "No session, or MFA not completed."},
        404: {"description": "Caller is not an administrator."},
        422: {"description": "A bound without a UTC offset, an empty range or over 366 days."},
    },
)
async def custom_request_funnel(
    from_: datetime | None = Query(
        default=None, alias="from", description="Inclusive; defaults to 90 days before `to`."
    ),
    to: datetime | None = Query(default=None, description="Exclusive; defaults to now."),
    session: AsyncSession = Depends(get_session),
) -> CustomRequestFunnelAnalytics:
    """A stage counts every lead that ever reached it, so a lost quote still counts as quoted."""
    check_range(from_, to, names=("from", "to"))
    upper = to or datetime.now(UTC)
    lower = from_ or upper - _DEFAULT_FUNNEL_SPAN
    if upper <= lower:
        raise invalid_query("to", "must be later than from")
    if upper - lower > _MAX_FUNNEL_SPAN:
        raise invalid_query("to", f"the range may span at most {_MAX_FUNNEL_SPAN.days} days")
    funnel = await SqlCustomRequestPipelineRepository(session).funnel(
        created_from=lower, created_to=upper
    )
    return CustomRequestFunnelAnalytics(
        from_=lower,
        to=upper,
        submitted=funnel.submitted,
        contacted=funnel.contacted,
        quoted=funnel.quoted,
        won=funnel.won,
        lost=funnel.lost,
        open=funnel.submitted - funnel.won - funnel.lost,
        quoted_total_cents=funnel.quoted_total_cents,
        won_total_cents=funnel.won_total_cents,
        currency=QUOTE_CURRENCY,
    )
