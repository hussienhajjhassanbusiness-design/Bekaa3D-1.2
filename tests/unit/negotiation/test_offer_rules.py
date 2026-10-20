"""Offer domain rules (VS-039; BR-080, BR-084, BR-089, BR-090; ADR-034)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.catalog.application.ports import CartProduct, ProductType
from app.catalog.domain.enums import PurchaseMode
from app.negotiation.domain.enums import (
    AWAITING_STATUSES,
    LIVE_STATUSES,
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
from app.negotiation.domain.offers import (
    Offer,
    OfferRefusal,
    check_amount,
    check_cooldown,
    check_offerable,
    expire,
    is_overdue,
    minimum_offer_cents,
    offer_refusal,
    open_offer,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
SECOND = timedelta(seconds=1)


_BASE = CartProduct(
    id=uuid.uuid4(),
    type=ProductType.STL,
    name="Dragon",
    slug="dragon",
    price_cents=1000,
    currency="USD",
    purchase_mode=None,
    is_available=True,
    max_quantity_per_line=None,
    listed=True,
)


def _product(**overrides: Any) -> CartProduct:
    return replace(_BASE, id=uuid.uuid4(), **overrides)


def _offer(status: OfferStatus, responds_by: datetime | None) -> Offer:
    turn = {OfferStatus.AWAITING_ADMIN: OfferTurn.ADMIN}.get(status, OfferTurn.CUSTOMER)
    return Offer(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        status=status,
        turn=turn if status in AWAITING_STATUSES else None,
        initial_amount_cents=800,
        current_amount_cents=800,
        agreed_amount_cents=None,
        currency="USD",
        responds_by=responds_by,
        accepted_at=None,
        checkout_expires_at=None,
        rejected_at=None,
        cooldown_until=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_live_statuses_are_the_glossary_three() -> None:
    assert {
        OfferStatus.AWAITING_ADMIN,
        OfferStatus.AWAITING_CUSTOMER,
        OfferStatus.ACCEPTED,
    } == LIVE_STATUSES


@pytest.mark.parametrize(
    ("product", "refusal"),
    [
        (None, OfferRefusal.NOT_LISTED),
        (_product(listed=False), OfferRefusal.NOT_LISTED),
        (
            _product(type=ProductType.PHYSICAL, purchase_mode=PurchaseMode.BOTH),
            OfferRefusal.NOT_NEGOTIABLE,
        ),
        (_product(is_available=False), OfferRefusal.UNAVAILABLE),
        (_product(), None),
    ],
)
def test_offer_refusal(product: CartProduct | None, refusal: OfferRefusal | None) -> None:
    assert offer_refusal(product) is refusal


def test_physical_is_refused_even_when_listed_and_available() -> None:
    product = _product(type=ProductType.PHYSICAL, purchase_mode=PurchaseMode.ONLINE_ONLY)
    with pytest.raises(OfferNotAllowedError) as caught:
        check_offerable(product, product.id)
    assert caught.value.reason == "not_negotiable"


@pytest.mark.parametrize(
    ("price", "percentage", "minimum"),
    [(1000, 70, 700), (999, 70, 700), (1001, 70, 701), (1000, 0, 0), (1000, 100, 1000)],
)
def test_minimum_rounds_up_to_a_whole_cent(price: int, percentage: int, minimum: int) -> None:
    assert minimum_offer_cents(price, percentage) == minimum


def test_amount_exactly_at_the_floor_is_accepted_and_one_below_is_not() -> None:
    check_amount(700, list_price_cents=1000, percentage=70)
    with pytest.raises(OfferBelowMinimumError) as caught:
        check_amount(699, list_price_cents=1000, percentage=70)
    assert caught.value.minimum_cents == 700


def test_floor_never_rounds_down() -> None:
    """999 * 70 % = 699.3: 699 must be refused, or the floor is below 70 %."""
    with pytest.raises(OfferBelowMinimumError):
        check_amount(699, list_price_cents=999, percentage=70)


def test_zero_percent_floor_allows_one_cent() -> None:
    check_amount(1, list_price_cents=1000, percentage=0)


def test_list_price_is_the_ceiling() -> None:
    check_amount(1000, list_price_cents=1000, percentage=70)
    with pytest.raises(OfferAboveListPriceError):
        check_amount(1001, list_price_cents=1000, percentage=70)


def test_free_product_cannot_be_offered_on() -> None:
    with pytest.raises(OfferAboveListPriceError):
        check_amount(1, list_price_cents=0, percentage=70)


def test_cooldown_boundaries() -> None:
    until = NOW
    with pytest.raises(OfferCooldownActiveError):
        check_cooldown([until], NOW - SECOND)
    check_cooldown([until], NOW)
    check_cooldown([until], NOW + SECOND)
    check_cooldown([], NOW)


def test_latest_rejection_rules_the_cooldown() -> None:
    with pytest.raises(OfferCooldownActiveError) as caught:
        check_cooldown([NOW - timedelta(days=1), NOW + timedelta(days=2)], NOW)
    assert caught.value.until == NOW + timedelta(days=2)


def test_open_offer_is_the_admins_turn_with_a_submitted_round() -> None:
    product, user = _product(), uuid.uuid4()
    new = open_offer(
        product,
        user_id=user,
        amount_cents=800,
        message="hi",
        percentage=70,
        response_window_seconds=172_800,
        now=NOW,
    )
    assert (new.status, new.turn) == (OfferStatus.AWAITING_ADMIN, OfferTurn.ADMIN)
    assert new.responds_by == NOW + timedelta(hours=48)
    first = new.first_round
    assert (first.sequence, first.actor, first.action) == (
        1,
        OfferActor.CUSTOMER,
        OfferAction.SUBMITTED,
    )
    assert (first.amount_cents, first.currency, first.message) == (800, "USD", "hi")


def test_open_offer_checks_the_amount() -> None:
    with pytest.raises(OfferBelowMinimumError):
        open_offer(
            _product(),
            user_id=uuid.uuid4(),
            amount_cents=1,
            message=None,
            percentage=70,
            response_window_seconds=3600,
            now=NOW,
        )


@pytest.mark.parametrize("status", sorted(AWAITING_STATUSES))
def test_overdue_boundaries(status: OfferStatus) -> None:
    offer = _offer(status, NOW)
    assert not is_overdue(offer, NOW - SECOND)
    assert is_overdue(offer, NOW)
    assert is_overdue(offer, NOW + SECOND)


@pytest.mark.parametrize("status", sorted(set(OfferStatus) - AWAITING_STATUSES))
def test_only_awaiting_offers_can_expire(status: OfferStatus) -> None:
    offer = _offer(status, NOW - timedelta(days=1))
    assert not is_overdue(offer, NOW)
    with pytest.raises(OfferNotExpirableError):
        expire(offer, next_sequence=2, now=NOW)


@pytest.mark.parametrize("status", sorted(AWAITING_STATUSES))
def test_expire_clears_the_turn_and_keeps_the_deadline(status: OfferStatus) -> None:
    offer = _offer(status, NOW - SECOND)
    expired, round_ = expire(offer, next_sequence=4, now=NOW)
    assert expired == replace(offer, status=OfferStatus.EXPIRED, turn=None, updated_at=NOW)
    assert (round_.sequence, round_.actor, round_.action) == (
        4,
        OfferActor.SYSTEM,
        OfferAction.EXPIRED,
    )
    assert round_.amount_cents is None and round_.currency is None


def test_expire_refuses_before_the_deadline() -> None:
    with pytest.raises(OfferNotExpirableError):
        expire(_offer(OfferStatus.AWAITING_ADMIN, NOW + SECOND), next_sequence=2, now=NOW)
