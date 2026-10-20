"""VS-041 offer rules: checkout window, paid, auto-close, and settling an STL purchase."""

import uuid
from datetime import timedelta
from typing import Any

import pytest

from app.negotiation.application.services.offer_checkout import (
    lock_for_checkout,
    read_for_checkout,
)
from app.negotiation.application.services.settle_offers import StlPurchase, settle_stl_purchases
from app.negotiation.domain.enums import LIVE_STATUSES, OfferAction, OfferActor, OfferStatus
from app.negotiation.domain.exceptions import (
    OfferCheckoutExpiredError,
    OfferInvalidTransitionError,
    OfferNotFoundError,
)
from app.negotiation.domain.offers import Offer, auto_close, check_checkout, mark_paid
from tests.unit.negotiation.offer_fakes import NOW, STL, USER, FakeAudit, FakeStore, make_offer

DEADLINE = NOW + timedelta(hours=1)


def _accepted(**over: Any) -> Offer:
    fields = {
        "status": OfferStatus.ACCEPTED,
        "turn": None,
        "responds_by": None,
        "agreed_amount_cents": 700,
        "accepted_at": NOW - timedelta(hours=1),
        "checkout_expires_at": DEADLINE,
    }
    return make_offer(**(fields | over))


@pytest.mark.parametrize(
    ("offset", "expired"),
    [(timedelta(seconds=-1), False), (timedelta(0), True), (timedelta(seconds=1), True)],
)
def test_checkout_window_closes_at_its_deadline(offset: timedelta, expired: bool) -> None:
    offer = _accepted()
    if expired:
        with pytest.raises(OfferCheckoutExpiredError):
            check_checkout(offer, DEADLINE + offset)
    else:
        check_checkout(offer, DEADLINE + offset)


def test_checkout_expired_is_410_even_before_its_deadline() -> None:
    with pytest.raises(OfferCheckoutExpiredError):
        check_checkout(_accepted(status=OfferStatus.CHECKOUT_EXPIRED), NOW)


@pytest.mark.parametrize(
    "status",
    [s for s in OfferStatus if s not in (OfferStatus.ACCEPTED, OfferStatus.CHECKOUT_EXPIRED)],
)
def test_any_other_status_cannot_be_checked_out(status: OfferStatus) -> None:
    with pytest.raises(OfferInvalidTransitionError) as caught:
        check_checkout(make_offer(status=status), NOW)
    assert caught.value.status is status


def test_mark_paid_keeps_the_agreed_price_and_records_it() -> None:
    offer = _accepted()
    paid, round_ = mark_paid(offer, next_sequence=4, now=NOW)
    assert (paid.status, paid.agreed_amount_cents, paid.checkout_expires_at) == (
        OfferStatus.PAID,
        700,
        DEADLINE,
    )
    assert (round_.actor, round_.action, round_.amount_cents, round_.sequence) == (
        OfferActor.SYSTEM,
        OfferAction.PAID,
        700,
        4,
    )


def test_mark_paid_refuses_anything_but_accepted() -> None:
    with pytest.raises(OfferInvalidTransitionError):
        mark_paid(_accepted(status=OfferStatus.CHECKOUT_EXPIRED), next_sequence=2, now=NOW)


@pytest.mark.parametrize("status", sorted(LIVE_STATUSES))
def test_auto_close_closes_every_live_status(status: OfferStatus) -> None:
    offer = make_offer(
        status=status, remind_at=NOW if status is OfferStatus.AWAITING_CUSTOMER else None
    )
    closed, round_ = auto_close(offer, next_sequence=2, now=NOW)
    assert (closed.status, closed.turn, closed.remind_at) == (OfferStatus.AUTO_CLOSED, None, None)
    assert (round_.actor, round_.action, round_.amount_cents) == (
        OfferActor.SYSTEM,
        OfferAction.AUTO_CLOSED,
        None,
    )


@pytest.mark.parametrize("status", [s for s in OfferStatus if s not in LIVE_STATUSES])
def test_auto_close_refuses_a_closed_offer(status: OfferStatus) -> None:
    with pytest.raises(OfferInvalidTransitionError):
        auto_close(make_offer(status=status), next_sequence=2, now=NOW)


async def test_read_and_lock_scope_to_the_owner_and_apply_the_window() -> None:
    store = FakeStore()
    offer = _accepted()
    store.offers[offer.id] = offer
    got = await read_for_checkout(store, offer_id=offer.id, user_id=USER, now=NOW)
    assert got is offer
    with pytest.raises(OfferNotFoundError):
        await lock_for_checkout(store, offer_id=uuid.uuid4(), user_id=USER, clock=lambda: NOW)
    with pytest.raises(OfferCheckoutExpiredError):
        await lock_for_checkout(store, offer_id=offer.id, user_id=USER, clock=lambda: DEADLINE)


async def test_lock_for_checkout_refuses_another_customers_offer() -> None:
    store = FakeStore()
    offer = _accepted(user_id=uuid.uuid4())
    store.offers[offer.id] = offer
    with pytest.raises(OfferNotFoundError):
        await lock_for_checkout(store, offer_id=offer.id, user_id=USER, clock=lambda: NOW)


async def test_settle_pays_the_offer_bought_through() -> None:
    store, audit = FakeStore(), FakeAudit()
    offer = _accepted()
    store.offers[offer.id] = offer
    order_id = uuid.uuid4()
    await settle_stl_purchases(
        store,
        audit,
        [StlPurchase(order_id, USER, STL.id, offer.id)],
        now=NOW,
    )
    assert store.offers[offer.id].status is OfferStatus.PAID
    [round_] = store.rounds_by_offer[offer.id]
    assert round_.action is OfferAction.PAID
    [row] = audit.rows
    assert (row["action"], row["actor_user_id"], row["after_data"]["order_id"]) == (
        "offer.paid",
        None,
        str(order_id),
    )
    assert store.acquisition_locks == [(USER, STL.id)]


@pytest.mark.parametrize("status", sorted(LIVE_STATUSES))
async def test_settle_auto_closes_a_live_offer_bought_another_way(status: OfferStatus) -> None:
    store, audit = FakeStore(), FakeAudit()
    offer = make_offer(status=status) if status is not OfferStatus.ACCEPTED else _accepted()
    store.offers[offer.id] = offer
    await settle_stl_purchases(
        store, audit, [StlPurchase(uuid.uuid4(), USER, STL.id, None)], now=NOW
    )
    assert store.offers[offer.id].status is OfferStatus.AUTO_CLOSED
    [row] = audit.rows
    assert (row["action"], row["before_data"]) == ("offer.auto_closed", {"status": status.value})


async def test_settle_leaves_other_customers_products_and_closed_offers() -> None:
    store, audit = FakeStore(), FakeAudit()
    others = [
        make_offer(user_id=uuid.uuid4()),
        make_offer(product_id=uuid.uuid4()),
        make_offer(status=OfferStatus.REJECTED),
    ]
    for offer in others:
        store.offers[offer.id] = offer
    await settle_stl_purchases(
        store, audit, [StlPurchase(uuid.uuid4(), USER, STL.id, None)], now=NOW
    )
    assert [store.offers[o.id] for o in others] == others
    assert not audit.rows


async def test_settle_takes_every_acquisition_lock_before_any_offer_in_product_order() -> None:
    store = FakeStore()
    products = [uuid.uuid4() for _ in range(3)]
    purchases = [StlPurchase(uuid.uuid4(), USER, p, None) for p in products]
    await settle_stl_purchases(store, FakeAudit(), purchases, now=NOW)
    assert store.acquisition_locks == [(USER, p) for p in sorted(products, key=lambda u: u.bytes)]


async def test_settle_never_refuses_a_payment_when_its_offer_is_not_accepted() -> None:
    """Defensive: the paid line stands; the offer is reported, not raised on (ADR-037)."""
    store, audit = FakeStore(), FakeAudit()
    offer = _accepted(status=OfferStatus.CHECKOUT_EXPIRED)
    store.offers[offer.id] = offer
    await settle_stl_purchases(
        store,
        audit,
        [StlPurchase(uuid.uuid4(), USER, STL.id, offer.id)],
        now=NOW,
    )
    assert store.offers[offer.id].status is OfferStatus.CHECKOUT_EXPIRED
    assert not audit.rows
