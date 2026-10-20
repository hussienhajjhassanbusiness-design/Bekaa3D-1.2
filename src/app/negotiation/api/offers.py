"""Customer offers (VS-039, FR-13, api-endpoints.md 13). Submitting needs a verified email,
CSRF and a per-user rate limit; reading needs only a session, like `GET /me/orders`."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)
from app.negotiation.api.cursors import decode_customer, encode_customer
from app.negotiation.api.offer_schemas import (
    OfferCreate,
    OfferDetailRead,
    OfferPage,
    OfferSummaryRead,
)
from app.negotiation.application.ports import CartProductReader, CustomerOfferFilters
from app.negotiation.application.services.offer_queries import customer_offers, offer_detail
from app.negotiation.application.services.submit_offer import OfferRequestContext, submit_offer
from app.negotiation.domain.enums import OfferStatus
from app.negotiation.domain.exceptions import (
    NegotiationDomainError,
    OfferAboveListPriceError,
    OfferAlreadyActiveError,
    OfferBelowMinimumError,
    OfferCooldownActiveError,
    OfferNotAllowedError,
    OfferProductOwnedError,
    OffersPausedError,
)
from app.negotiation.infrastructure.adapters import (
    EngagementOfferNotifier,
    OrderingStlOwnership,
)
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.platform.public import SqlAuditWriter, settings_reader

submit_router = APIRouter(prefix="/offers", tags=["offers"])
router = APIRouter(prefix="/me/offers", tags=["offers"])

# SEC-11 / ADR-034: generous for a real customer, a wall for a script.
RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 3600
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


def _translate(exc: NegotiationDomainError) -> ApiError | RequestValidationError:
    if isinstance(exc, OffersPausedError):
        return ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ORDERS_PAUSED",
            title="Orders are paused",
            detail="The shop is not accepting orders or offers right now.",
        )
    if isinstance(exc, OfferNotAllowedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="PRODUCT_NOT_PURCHASABLE",
            title="Product cannot be offered on",
            detail="Offers are open only on available STL products.",
            extensions={"reason": exc.reason},
        )
    if isinstance(exc, OfferProductOwnedError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="PRODUCT_ALREADY_OWNED",
            title="STL already owned",
            detail="You already own this STL.",
        )
    if isinstance(exc, OfferAlreadyActiveError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="OFFER_ALREADY_ACTIVE",
            title="Offer already active",
            detail="You already have a live offer on this product.",
        )
    if isinstance(exc, OfferBelowMinimumError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="OFFER_BELOW_MINIMUM",
            title="Offer below the minimum",
            detail="The offer is below the minimum allowed for this product.",
            extensions={"minimum": {"amount_cents": exc.minimum_cents, "currency": "USD"}},
        )
    if isinstance(exc, OfferCooldownActiveError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="OFFER_COOLDOWN_ACTIVE",
            title="Offer cooldown active",
            detail="A recent offer on this product was rejected; try again later.",
            extensions={"cooldown_until": exc.until.isoformat()},
        )
    if isinstance(exc, OfferAboveListPriceError):
        return RequestValidationError(
            [
                {
                    "loc": ("body", "amount_cents"),
                    "msg": f"must not exceed the list price ({exc.list_price_cents} cents)",
                    "type": "value_error",
                }
            ]
        )
    raise exc


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
    offers = SqlOfferStore(session)
    ip = client_ip(request)
    try:
        offer = await submit_offer(
            offers=offers,
            products=products,
            ownership=OrderingStlOwnership(session),
            settings=settings_reader(session),
            notifier=EngagementOfferNotifier(session),
            audit=SqlAuditWriter(session),
            user_id=user.id,
            product_id=body.product_id,
            amount_cents=body.amount_cents,
            message=body.message,
            now=datetime.now(UTC),
            context=OfferRequestContext(
                request_id=getattr(request.state, "request_id", None),
                ip_hash=hash_ip(ip) if ip else None,
            ),
        )
    except NegotiationDomainError as exc:
        raise _translate(exc) from exc
    view = await offer_detail(offers, products, offer_id=offer.id, user_id=user.id)
    if view is None:  # pragma: no cover - inserted above in this transaction
        raise not_found_error()
    return OfferDetailRead.of(view, get_settings().media_public_url)


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
    view = await offer_detail(SqlOfferStore(session), products, offer_id=offer_id, user_id=user.id)
    if view is None:
        raise not_found_error()
    return OfferDetailRead.of(view, get_settings().media_public_url)
