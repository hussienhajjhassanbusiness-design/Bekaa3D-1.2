"""Offer rules (SRS 11, 20.6; BR-080 to BR-092). Pure: no framework or database imports."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.catalog.application.ports import CartProduct, ProductType
from app.negotiation.domain.enums import (
    AWAITING_STATUSES,
    LIVE_STATUSES,
    OfferAction,
    OfferActor,
    OfferStatus,
    OfferTurn,
)
from app.negotiation.domain.exceptions import (
    NegotiationDomainError,
    OfferAboveListPriceError,
    OfferAmountChangedError,
    OfferBelowMinimumError,
    OfferCheckoutExpiredError,
    OfferCooldownActiveError,
    OfferExpiredError,
    OfferInvalidTransitionError,
    OfferNotAllowedError,
    OfferNotExpirableError,
    OfferNotYourTurnError,
)

ENTITY_TYPE = "Offer"
CURRENCY = "USD"
MAX_MESSAGE_LENGTH = 1000


class OfferRefusal(StrEnum):
    NOT_LISTED = "not_listed"
    UNAVAILABLE = "unavailable"
    NOT_NEGOTIABLE = "not_negotiable"


class OfferMove(StrEnum):
    """What a party may do; also the strings `allowed_actions` lists."""

    COUNTER = "counter"
    ACCEPT = "accept"
    REJECT = "reject"
    WITHDRAW = "withdraw"


# SRS 20.6: the customer never rejects (they withdraw); the administrator never withdraws.
MOVES: dict[OfferActor, tuple[OfferMove, ...]] = {
    OfferActor.CUSTOMER: (OfferMove.COUNTER, OfferMove.ACCEPT, OfferMove.WITHDRAW),
    OfferActor.ADMIN: (OfferMove.COUNTER, OfferMove.ACCEPT, OfferMove.REJECT),
}


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
    remind_at: datetime | None = None


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
    expired = replace(offer, status=OfferStatus.EXPIRED, turn=None, remind_at=None, updated_at=now)
    return expired, NewRound(next_sequence, OfferActor.SYSTEM, OfferAction.EXPIRED)


def check_move(offer: Offer, actor: OfferActor, move: OfferMove, now: datetime) -> None:
    """ADR-035 order: expired (410), then closed or accepted (409), then the turn (409)."""
    if move not in MOVES[actor]:
        raise OfferInvalidTransitionError(offer.status)
    if offer.status is OfferStatus.EXPIRED or is_overdue(offer, now):
        raise OfferExpiredError()
    if offer.status not in AWAITING_STATUSES:
        raise OfferInvalidTransitionError(offer.status)
    # BR-092: a pending offer may be withdrawn whoever's turn it is (ADR-034 d8).
    if move is not OfferMove.WITHDRAW and (offer.turn is None or offer.turn.value != actor.value):
        raise OfferNotYourTurnError()


def allowed_moves(offer: Offer, actor: OfferActor, now: datetime) -> list[OfferMove]:
    allowed = []
    for move in MOVES[actor]:
        try:
            check_move(offer, actor, move, now)
        except NegotiationDomainError:
            continue
        allowed.append(move)
    return allowed


def check_negotiable(product: CartProduct | None, product_id: UUID) -> CartProduct:
    """At counter and accept: still offerable, and not free (no positive amount fits under 0)."""
    product = check_offerable(product, product_id)
    if product.price_cents <= 0:
        raise OfferNotAllowedError(product_id, str(OfferRefusal.NOT_NEGOTIABLE))
    return product


def reminder_at(start: datetime, deadline: datetime) -> datetime:
    """75 % of the way through the customer's turn (VS-040)."""
    return deadline - (deadline - start) / 4


def counter(
    offer: Offer,
    *,
    actor: OfferActor,
    amount_cents: int,
    message: str | None,
    list_price_cents: int,
    percentage: int,
    response_window_seconds: int,
    next_sequence: int,
    now: datetime,
) -> tuple[Offer, NewRound]:
    """Switches the turn and resets `responds_by` (BR-083); only a customer meets the floor."""
    check_move(offer, actor, OfferMove.COUNTER, now)
    if actor is OfferActor.CUSTOMER:
        check_amount(amount_cents, list_price_cents=list_price_cents, percentage=percentage)
    elif amount_cents > list_price_cents:
        raise OfferAboveListPriceError(list_price_cents)
    deadline = now + timedelta(seconds=response_window_seconds)
    to_customer = actor is OfferActor.ADMIN
    countered = replace(
        offer,
        status=OfferStatus.AWAITING_CUSTOMER if to_customer else OfferStatus.AWAITING_ADMIN,
        turn=OfferTurn.CUSTOMER if to_customer else OfferTurn.ADMIN,
        current_amount_cents=amount_cents,
        responds_by=deadline,
        remind_at=reminder_at(now, deadline) if to_customer else None,
        updated_at=now,
    )
    return countered, NewRound(next_sequence, actor, OfferAction.COUNTERED, amount_cents, message)


def check_amount_seen(offer: Offer, expected_amount_cents: int) -> None:
    """Accept binds only the amount the caller saw; a stale page is refused (ADR-035 d9)."""
    if expected_amount_cents != offer.current_amount_cents:
        raise OfferAmountChangedError(offer.current_amount_cents)


def accept(
    offer: Offer,
    *,
    actor: OfferActor,
    expected_amount_cents: int,
    list_price_cents: int,
    checkout_window_seconds: int,
    next_sequence: int,
    now: datetime,
) -> tuple[Offer, NewRound]:
    """Freezes the agreed price (BR-085), never above today's list price (ADR-035)."""
    check_move(offer, actor, OfferMove.ACCEPT, now)
    check_amount_seen(offer, expected_amount_cents)
    agreed = min(offer.current_amount_cents, list_price_cents)
    accepted = replace(
        offer,
        status=OfferStatus.ACCEPTED,
        turn=None,
        agreed_amount_cents=agreed,
        accepted_at=now,
        checkout_expires_at=now + timedelta(seconds=checkout_window_seconds),
        responds_by=None,
        remind_at=None,
        updated_at=now,
    )
    return accepted, NewRound(next_sequence, actor, OfferAction.ACCEPTED, agreed)


def reject(
    offer: Offer, *, reason: str | None, cooldown_seconds: int, next_sequence: int, now: datetime
) -> tuple[Offer, NewRound]:
    """Arms the cooldown in the same write as the status (BR-089, ADR-034 d5)."""
    check_move(offer, OfferActor.ADMIN, OfferMove.REJECT, now)
    rejected = replace(
        offer,
        status=OfferStatus.REJECTED,
        turn=None,
        rejected_at=now,
        cooldown_until=now + timedelta(seconds=cooldown_seconds),
        remind_at=None,
        updated_at=now,
    )
    round_ = NewRound(next_sequence, OfferActor.ADMIN, OfferAction.REJECTED, message=reason)
    return rejected, round_


def withdraw(
    offer: Offer, *, reason: str | None, next_sequence: int, now: datetime
) -> tuple[Offer, NewRound]:
    check_move(offer, OfferActor.CUSTOMER, OfferMove.WITHDRAW, now)
    withdrawn = replace(
        offer, status=OfferStatus.WITHDRAWN, turn=None, remind_at=None, updated_at=now
    )
    round_ = NewRound(next_sequence, OfferActor.CUSTOMER, OfferAction.WITHDRAWN, message=reason)
    return withdrawn, round_


def is_checkout_over(offer: Offer, now: datetime) -> bool:
    """BR-086: the window has closed once `now >= checkout_expires_at`."""
    return (
        offer.status is OfferStatus.ACCEPTED
        and offer.checkout_expires_at is not None
        and now >= offer.checkout_expires_at
    )


def expire_checkout(offer: Offer, *, next_sequence: int, now: datetime) -> tuple[Offer, NewRound]:
    """`accepted -> checkout_expired`; the agreed price and the deadline stay."""
    if not is_checkout_over(offer, now):
        raise OfferNotExpirableError(offer.status)
    closed = replace(offer, status=OfferStatus.CHECKOUT_EXPIRED, updated_at=now)
    return closed, NewRound(next_sequence, OfferActor.SYSTEM, OfferAction.CHECKOUT_EXPIRED)


def check_checkout(offer: Offer, now: datetime) -> None:
    """VS-041: 410 once the window has closed (whether or not the job has run), else 409
    unless accepted. Read under the offer lock with a clock read after it."""
    if offer.status is OfferStatus.CHECKOUT_EXPIRED or is_checkout_over(offer, now):
        raise OfferCheckoutExpiredError()
    if offer.status is not OfferStatus.ACCEPTED:
        raise OfferInvalidTransitionError(offer.status)


def mark_paid(offer: Offer, *, next_sequence: int, now: datetime) -> tuple[Offer, NewRound]:
    """`accepted -> paid` (SRS 5.4 step 6): the round records the agreed amount paid."""
    if offer.status is not OfferStatus.ACCEPTED:
        raise OfferInvalidTransitionError(offer.status)
    paid = replace(offer, status=OfferStatus.PAID, updated_at=now)
    round_ = NewRound(next_sequence, OfferActor.SYSTEM, OfferAction.PAID, offer.agreed_amount_cents)
    return paid, round_


def auto_close(offer: Offer, *, next_sequence: int, now: datetime) -> tuple[Offer, NewRound]:
    """BR-088, SRS 11.4: any live offer closes once the STL is bought another way."""
    if offer.status not in LIVE_STATUSES:
        raise OfferInvalidTransitionError(offer.status)
    closed = replace(
        offer, status=OfferStatus.AUTO_CLOSED, turn=None, remind_at=None, updated_at=now
    )
    return closed, NewRound(next_sequence, OfferActor.SYSTEM, OfferAction.AUTO_CLOSED)


def is_reminder_due(offer: Offer, now: datetime) -> bool:
    """Due at `remind_at`, and only while the turn is still open; past it, expiry takes over."""
    return (
        offer.status is OfferStatus.AWAITING_CUSTOMER
        and offer.remind_at is not None
        and now >= offer.remind_at
        and not is_overdue(offer, now)
    )
