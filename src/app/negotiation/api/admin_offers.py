"""The administrator's offer queue and answers (VS-039, VS-040, api-endpoints.md 21). Every
route sits behind the admin boundary; writes also need CSRF. Queue order: ADR-034."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.negotiation.api.cursors import decode_queue, encode_queue, utc
from app.negotiation.api.offer_errors import translate
from app.negotiation.api.offer_schemas import (
    AdminOfferDetailRead,
    AdminOfferPage,
    AdminOfferSummaryRead,
    OfferAcceptRequest,
    OfferCounterRequest,
    OfferReasonRequest,
)
from app.negotiation.api.wiring import offer_deps, request_context
from app.negotiation.application.ports import AdminOfferFilters, CartProductReader, OfferStore
from app.negotiation.application.services.offer_queries import admin_queue, offer_detail
from app.negotiation.application.services.respond_to_offer import (
    Responder,
    accept_offer,
    counter_offer,
    reject_offer,
)
from app.negotiation.domain.enums import OfferActor, OfferStatus
from app.negotiation.domain.exceptions import NegotiationDomainError
from app.negotiation.infrastructure.adapters import IdentityCustomerDirectory
from app.negotiation.infrastructure.offers import SqlOfferStore

admin_router = APIRouter(prefix="/offers", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown id, or caller is not an administrator."},
}
_ACTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESPONSES,
    403: {"description": "CSRF token missing or invalid."},
    409: {
        "description": "OFFER_NOT_YOUR_TURN, INVALID_STATE_TRANSITION (with `offer_status`), "
        "OFFER_AMOUNT_CHANGED (accept, with `current_amount`), or PRODUCT_ALREADY_OWNED (accept)."
    },
    410: {"description": "OFFER_EXPIRED: the response deadline has passed."},
    422: {
        "description": "PRODUCT_NOT_PURCHASABLE (with `reason`), or VALIDATION_ERROR "
        "(including an amount above the list price)."
    },
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
        default=None, description="Pending offers due before this (exclusive), with a UTC offset."
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
    return await _detail(SqlOfferStore(session), products, session, offer_id, datetime.now(UTC))


async def _detail(
    offers: OfferStore,
    products: CartProductReader,
    session: AsyncSession,
    offer_id: UUID,
    now: datetime,
) -> AdminOfferDetailRead:
    view = await offer_detail(
        offers, products, offer_id=offer_id, customers=IdentityCustomerDirectory(session), now=now
    )
    if view is None:
        raise not_found_error()
    return AdminOfferDetailRead.of(view, get_settings().media_public_url)


@admin_router.post(
    "/{offer_id}/counter",
    response_model=AdminOfferDetailRead,
    dependencies=[Depends(require_csrf)],
    summary="Counter the customer's amount; the turn passes to them",
    responses=_ACTION_RESPONSES,
)
async def counter(
    offer_id: UUID,
    body: OfferCounterRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> AdminOfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.ADMIN, claims.user_id, request_context(request))
    try:
        await counter_offer(
            deps,
            who,
            offer_id=offer_id,
            amount_cents=body.amount_cents,
            message=body.message,
        )
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, session, offer_id, datetime.now(UTC))


@admin_router.post(
    "/{offer_id}/accept",
    response_model=AdminOfferDetailRead,
    dependencies=[Depends(require_csrf)],
    summary="Accept the customer's amount (capped at today's list price)",
    responses=_ACTION_RESPONSES,
)
async def accept(
    offer_id: UUID,
    request: Request,
    body: OfferAcceptRequest,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> AdminOfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.ADMIN, claims.user_id, request_context(request))
    try:
        await accept_offer(
            deps, who, offer_id=offer_id, expected_amount_cents=body.expected_amount_cents
        )
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, session, offer_id, datetime.now(UTC))


@admin_router.post(
    "/{offer_id}/reject",
    response_model=AdminOfferDetailRead,
    dependencies=[Depends(require_csrf)],
    summary="Reject the offer; starts the customer's cooldown on this product",
    responses=_ACTION_RESPONSES,
)
async def reject(
    offer_id: UUID,
    request: Request,
    body: OfferReasonRequest | None = None,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> AdminOfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.ADMIN, claims.user_id, request_context(request))
    reason = body.reason if body is not None else None
    try:
        await reject_offer(deps, who, offer_id=offer_id, reason=reason)
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, session, offer_id, datetime.now(UTC))
