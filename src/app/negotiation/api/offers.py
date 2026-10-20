"""Customer offers (VS-039, VS-040, FR-13, api-endpoints.md 13). Writing needs a verified
email, CSRF and a per-user rate limit; reading needs only a session, like `GET /me/orders`."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)
from app.negotiation.api.cursors import decode_customer, encode_customer
from app.negotiation.api.offer_errors import translate
from app.negotiation.api.offer_schemas import (
    OfferCounterRequest,
    OfferCreate,
    OfferDetailRead,
    OfferPage,
    OfferReasonRequest,
    OfferSummaryRead,
)
from app.negotiation.api.wiring import offer_deps, request_context
from app.negotiation.application.ports import (
    CartProductReader,
    CustomerOfferFilters,
    OfferStore,
)
from app.negotiation.application.services.offer_queries import customer_offers, offer_detail
from app.negotiation.application.services.respond_to_offer import (
    Responder,
    accept_offer,
    counter_offer,
    withdraw_offer,
)
from app.negotiation.application.services.submit_offer import submit_offer
from app.negotiation.domain.enums import OfferActor, OfferStatus
from app.negotiation.domain.exceptions import NegotiationDomainError
from app.negotiation.infrastructure.offers import SqlOfferStore

submit_router = APIRouter(prefix="/offers", tags=["offers"])
router = APIRouter(prefix="/me/offers", tags=["offers"])

# SEC-11 / ADR-034: generous for a real customer, a wall for a script.
RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 3600
# ADR-035: a live negotiation answers more often than it opens; its own bucket.
ACTION_RATE_LIMIT = 60
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}
_SUBMIT_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    409: {"description": "OFFER_ALREADY_ACTIVE, or PRODUCT_ALREADY_OWNED."},
    422: {
        "description": "OFFER_BELOW_MINIMUM (with `minimum`), OFFER_COOLDOWN_ACTIVE (with "
        "`cooldown_until`), PRODUCT_NOT_PURCHASABLE (with `reason`), or VALIDATION_ERROR."
    },
    429: {"description": "RATE_LIMITED: too many offers this hour."},
    503: {"description": "ORDERS_PAUSED: the shop is not accepting orders or offers."},
}
_ACTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    404: {"description": "No such offer among the caller's own."},
    409: {
        "description": "OFFER_NOT_YOUR_TURN, INVALID_STATE_TRANSITION (with `offer_status`), or "
        "PRODUCT_ALREADY_OWNED (accept)."
    },
    410: {"description": "OFFER_EXPIRED: the response deadline has passed."},
    422: {
        "description": "OFFER_BELOW_MINIMUM, PRODUCT_NOT_PURCHASABLE (with `reason`), or "
        "VALIDATION_ERROR (including an amount above the list price)."
    },
    429: {"description": "RATE_LIMITED: too many offer actions this hour."},
}


async def _offer_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user; after `current_verified_user`, so an unverified caller spends no budget."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="offers",
        subject=str(user.id),
        limit=RATE_LIMIT,
        window_seconds=RATE_WINDOW_SECONDS,
    )


async def _action_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    await enforce_rate_limit(
        request,
        response,
        key_prefix="offer_actions",
        subject=str(user.id),
        limit=ACTION_RATE_LIMIT,
        window_seconds=RATE_WINDOW_SECONDS,
    )


async def _detail(
    offers: OfferStore, products: CartProductReader, offer_id: UUID, user: User, now: datetime
) -> OfferDetailRead:
    view = await offer_detail(offers, products, offer_id=offer_id, user_id=user.id, now=now)
    if view is None:  # pragma: no cover - written above in this transaction
        raise not_found_error()
    return OfferDetailRead.of(view, get_settings().media_public_url)


@submit_router.post(
    "",
    response_model=OfferDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_offer_rate_limit), Depends(require_csrf)],
    summary="Open a price offer on an STL product",
    responses=_SUBMIT_RESPONSES,
)
async def create_offer(
    body: OfferCreate,
    request: Request,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferDetailRead:
    deps, now = offer_deps(session, products), datetime.now(UTC)
    try:
        offer = await submit_offer(
            offers=deps.offers,
            products=products,
            ownership=deps.ownership,
            settings=deps.settings,
            notifier=deps.notifier,
            audit=deps.audit,
            user_id=user.id,
            product_id=body.product_id,
            amount_cents=body.amount_cents,
            message=body.message,
            now=now,
            context=request_context(request),
        )
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, offer.id, user, now)


@router.get(
    "",
    response_model=OfferPage,
    summary="List the caller's own offers, newest first",
    responses={**_READ_RESPONSES, 422: {"description": "Invalid filter or cursor."}},
)
async def list_my_offers(
    status_filter: OfferStatus | None = Query(default=None, alias="status"),
    product_id: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferPage:
    rows = await customer_offers(
        SqlOfferStore(session),
        products,
        user_id=user.id,
        filters=CustomerOfferFilters(status=status_filter, product_id=product_id),
        after=decode_customer(cursor),
        limit=limit + 1,
    )
    page, base = rows[:limit], get_settings().media_public_url
    last = page[-1].offer if len(rows) > limit else None
    return OfferPage(
        items=[OfferSummaryRead.of(row, base) for row in page],
        next_cursor=encode_customer(last.created_at, last.id) if last is not None else None,
    )


@router.get(
    "/{offer_id}",
    response_model=OfferDetailRead,
    summary="One of the caller's own offers, with its complete history",
    responses={**_READ_RESPONSES, 404: {"description": "No such offer among the caller's own."}},
)
async def get_my_offer(
    offer_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferDetailRead:
    view = await offer_detail(
        SqlOfferStore(session), products, offer_id=offer_id, user_id=user.id, now=datetime.now(UTC)
    )
    if view is None:
        raise not_found_error()
    return OfferDetailRead.of(view, get_settings().media_public_url)


@router.post(
    "/{offer_id}/counter",
    response_model=OfferDetailRead,
    dependencies=[Depends(_action_rate_limit), Depends(require_csrf)],
    summary="Counter the administrator's amount; the turn passes to them",
    responses=_ACTION_RESPONSES,
)
async def counter_my_offer(
    offer_id: UUID,
    body: OfferCounterRequest,
    request: Request,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.CUSTOMER, user.id, request_context(request))
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
    return await _detail(deps.offers, products, offer_id, user, datetime.now(UTC))


@router.post(
    "/{offer_id}/accept",
    response_model=OfferDetailRead,
    dependencies=[Depends(_action_rate_limit), Depends(require_csrf)],
    summary="Accept the administrator's amount; opens the one-time checkout window",
    responses=_ACTION_RESPONSES,
)
async def accept_my_offer(
    offer_id: UUID,
    request: Request,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.CUSTOMER, user.id, request_context(request))
    try:
        await accept_offer(deps, who, offer_id=offer_id)
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, offer_id, user, datetime.now(UTC))


@router.post(
    "/{offer_id}/withdraw",
    response_model=OfferDetailRead,
    dependencies=[Depends(_action_rate_limit), Depends(require_csrf)],
    summary="Withdraw a pending offer, whoever's turn it is",
    responses=_ACTION_RESPONSES,
)
async def withdraw_my_offer(
    offer_id: UUID,
    request: Request,
    body: OfferReasonRequest | None = None,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> OfferDetailRead:
    deps = offer_deps(session, products)
    who = Responder(OfferActor.CUSTOMER, user.id, request_context(request))
    reason = body.reason if body is not None else None
    try:
        await withdraw_offer(deps, who, offer_id=offer_id, reason=reason)
    except NegotiationDomainError as exc:
        raise translate(exc) from exc
    return await _detail(deps.offers, products, offer_id, user, datetime.now(UTC))
