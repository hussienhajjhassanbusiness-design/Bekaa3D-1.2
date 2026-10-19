"""The administrator's offer queue (VS-039, api-endpoints.md 21). Every route sits behind
the admin boundary; the queue order and filters are ADR-034's."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.identity.public import AdminBoundaryRoute, not_found_error
from app.negotiation.api.cursors import decode_queue, encode_queue, utc
from app.negotiation.api.offer_schemas import (
    AdminOfferDetailRead,
    AdminOfferPage,
    AdminOfferSummaryRead,
)
from app.negotiation.application.ports import AdminOfferFilters, CartProductReader
from app.negotiation.application.services.offer_queries import admin_queue, offer_detail
from app.negotiation.domain.enums import OfferStatus
from app.negotiation.infrastructure.adapters import IdentityCustomerDirectory
from app.negotiation.infrastructure.offers import SqlOfferStore

admin_router = APIRouter(prefix="/offers", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown id, or caller is not an administrator."},
}


@admin_router.get(
    "",
    response_model=AdminOfferPage,
    summary="The offer queue: the administrator's turn first, soonest deadline first",
    responses={**_RESPONSES, 422: {"description": "Invalid filter or a tampered cursor."}},
)
async def list_offers(
    status_filter: OfferStatus | None = Query(default=None, alias="status"),
    product_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None, description="The customer who made the offer."),
    responds_before: datetime | None = Query(
        default=None, description="Exclusive deadline bound; must carry a UTC offset."
    ),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> AdminOfferPage:
    filters = AdminOfferFilters(
        status=status_filter,
        product_id=product_id,
        user_id=user_id,
        responds_before=utc(responds_before, "responds_before"),
    )
    rows = await admin_queue(
        SqlOfferStore(session),
        products,
        IdentityCustomerDirectory(session),
        filters=filters,
        after=decode_queue(cursor),
        limit=limit + 1,
    )
    page, base = rows[:limit], get_settings().media_public_url
    return AdminOfferPage(
        items=[AdminOfferSummaryRead.of(view, base) for view, _ in page],
        next_cursor=encode_queue(page[-1][1]) if len(rows) > limit else None,
    )


@admin_router.get(
    "/{offer_id}",
    response_model=AdminOfferDetailRead,
    summary="One offer with its complete negotiation history",
    responses=_RESPONSES,
)
async def get_offer(
    offer_id: UUID,
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> AdminOfferDetailRead:
    view = await offer_detail(
        SqlOfferStore(session),
        products,
        offer_id=offer_id,
        customers=IdentityCustomerDirectory(session),
    )
    if view is None:
        raise not_found_error()
    return AdminOfferDetailRead.of(view, get_settings().media_public_url)
