"""Negotiation errors as stable API codes (api-endpoints.md 4; docs/offers.md)."""

from fastapi import status
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import ApiError
from app.identity.public import not_found_error
from app.negotiation.domain.exceptions import (
    NegotiationDomainError,
    OfferAboveListPriceError,
    OfferAlreadyActiveError,
    OfferBelowMinimumError,
    OfferCooldownActiveError,
    OfferExpiredError,
    OfferInvalidTransitionError,
    OfferNotAllowedError,
    OfferNotFoundError,
    OfferNotYourTurnError,
    OfferProductOwnedError,
    OffersPausedError,
)


def translate(exc: NegotiationDomainError) -> ApiError | RequestValidationError:
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
    if isinstance(exc, OfferNotFoundError):
        return not_found_error()
    if isinstance(exc, OfferExpiredError):
        return ApiError(
            status_code=status.HTTP_410_GONE,
            code="OFFER_EXPIRED",
            title="Offer expired",
            detail="The response deadline for this offer has passed.",
        )
    if isinstance(exc, OfferNotYourTurnError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="OFFER_NOT_YOUR_TURN",
            title="Not your turn",
            detail="The other party has to answer this offer first.",
        )
    if isinstance(exc, OfferInvalidTransitionError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Offer cannot be answered",
            detail=f"An offer that is {exc.status.value} cannot be answered.",
            extensions={"offer_status": exc.status.value},
        )
    raise exc
