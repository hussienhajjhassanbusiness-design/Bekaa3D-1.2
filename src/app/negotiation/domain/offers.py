"""Offer rules (SRS 11, 20.6; BR-080 to BR-092). Pure: no framework or database imports."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.catalog.application.ports import CartProduct, ProductType
from app.negotiation.domain.enums import (
    AWAITING_STATUSES,
    OfferAction,
    OfferActor,
    OfferStatus,
    OfferTurn,
)
from app.negotiation.domain.exceptions import (
    OfferAboveListPriceError,
    OfferBelowMinimumError,
    OfferCooldownActiveError,
    OfferNotAllowedError,
    OfferNotExpirableError,
)

ENTITY_TYPE = "Offer"
CURRENCY = "USD"
MAX_MESSAGE_LENGTH = 1000


class OfferRefusal(StrEnum):
    NOT_LISTED = "not_listed"
    UNAVAILABLE = "unavailable"
    NOT_NEGOTIABLE = "not_negotiable"


@dataclass(frozen=True)
class Offer:
    id: UUID
    user_id: UUID
    product_id: UUID
    status: OfferStatus
    turn: OfferTurn | None
    initial_amount_cents: int
    current_amount_cents: int
    agreed_amount_cents: int | None
    currency: str
    responds_by: datetime | None
    accepted_at: datetime | None
    checkout_expires_at: datetime | None
    rejected_at: datetime | None
    cooldown_until: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OfferRound:
    id: UUID
    offer_id: UUID
    sequence: int
    actor: OfferActor
    action: OfferAction
    amount_cents: int | None
    currency: str | None
    message: str | None
    created_at: datetime


@dataclass(frozen=True)
class NewRound:
    sequence: int
    actor: OfferActor
    action: OfferAction
    amount_cents: int | None = None
    message: str | None = None

    @property
    def currency(self) -> str | None:
        return CURRENCY if self.amount_cents is not None else None


@dataclass(frozen=True)
class NewOffer:
    """Always opens on the administrator's turn (SRS 5.4 step 2)."""

    user_id: UUID
    product_id: UUID
    amount_cents: int
    responds_by: datetime
    first_round: NewRound
    status: OfferStatus = OfferStatus.AWAITING_ADMIN
    turn: OfferTurn = OfferTurn.ADMIN
    currency: str = CURRENCY


def offer_refusal(product: CartProduct | None) -> OfferRefusal | None:
    """None iff an offer may be opened; as strict as ADR-022's `can_offer`."""
    if product is None or not product.listed:
        return OfferRefusal.NOT_LISTED
    if product.type is not ProductType.STL:
        return OfferRefusal.NOT_NEGOTIABLE
    if not product.is_available:
        return OfferRefusal.UNAVAILABLE
    return None


def minimum_offer_cents(list_price_cents: int, percentage: int) -> int:
    """The smallest whole-cent amount at or above `percentage` of the price; integers only."""
    return -(-list_price_cents * percentage // 100)


def check_amount(amount_cents: int, *, list_price_cents: int, percentage: int) -> None:
    if amount_cents > list_price_cents:
        raise OfferAboveListPriceError(list_price_cents)
    minimum = minimum_offer_cents(list_price_cents, percentage)
    if amount_cents < minimum:
        raise OfferBelowMinimumError(minimum)


def check_cooldown(cooldowns: Iterable[datetime], now: datetime) -> None:
    """BR-089: the latest rejection rules; a cooldown ending exactly now has ended."""
    until = max(cooldowns, default=None)
    if until is not None and now < until:
        raise OfferCooldownActiveError(until)


def open_offer(
    product: CartProduct,
    *,
    user_id: UUID,
    amount_cents: int,
    message: str | None,
    percentage: int,
    response_window_seconds: int,
    now: datetime,
) -> NewOffer:
    """Caller has already refused the product via `offer_refusal`."""
    check_amount(amount_cents, list_price_cents=product.price_cents, percentage=percentage)
    return NewOffer(
        user_id=user_id,
        product_id=product.id,
        amount_cents=amount_cents,
        responds_by=now + timedelta(seconds=response_window_seconds),
        first_round=NewRound(
            sequence=1,
            actor=OfferActor.CUSTOMER,
            action=OfferAction.SUBMITTED,
            amount_cents=amount_cents,
            message=message,
        ),
    )


def check_offerable(product: CartProduct | None, product_id: UUID) -> CartProduct:
    refusal = offer_refusal(product)
    if refusal is not None or product is None:
        raise OfferNotAllowedError(product_id, str(refusal or OfferRefusal.NOT_LISTED))
    return product


def is_overdue(offer: Offer, now: datetime) -> bool:
    """BR-084: the turn's deadline has been reached (expired at `now >= responds_by`)."""
    return (
        offer.status in AWAITING_STATUSES
        and offer.responds_by is not None
        and now >= offer.responds_by
    )


def expire(offer: Offer, *, next_sequence: int, now: datetime) -> tuple[Offer, NewRound]:
    """`awaiting_* -> expired` with its `system` round; `responds_by` keeps the deadline."""
    if not is_overdue(offer, now):
        raise OfferNotExpirableError(offer.status)
    expired = replace(offer, status=OfferStatus.EXPIRED, turn=None, updated_at=now)
    return expired, NewRound(next_sequence, OfferActor.SYSTEM, OfferAction.EXPIRED)
