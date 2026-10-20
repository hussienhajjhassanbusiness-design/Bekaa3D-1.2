"""VS-040's services over in-memory fakes: who is told what, by which channel, and that a
refused action writes nothing (FR-13 failure behaviour; ADR-035)."""

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from app.catalog.application.ports import CartProduct
from app.negotiation.application.services.expire_offers import (
    EXPIRING_SOON_TEMPLATE,
    expire_checkout_offer,
    remind_offer,
)
from app.negotiation.application.services.respond_to_offer import (
    ACCEPTED_TEMPLATE,
    COUNTERED_TEMPLATE,
    REJECTED_TEMPLATE,
    OfferDeps,
    Responder,
    accept_offer,
    counter_offer,
    reject_offer,
    withdraw_offer,
)
from app.negotiation.domain.enums import OfferAction, OfferActor, OfferStatus, OfferTurn
from app.negotiation.domain.exceptions import (
    OfferAmountChangedError,
    OfferExpiredError,
    OfferInvalidTransitionError,
    OfferNotAllowedError,
    OfferNotFoundError,
    OfferNotYourTurnError,
    OfferProductOwnedError,
)
from app.negotiation.domain.offers import Offer
from tests.unit.negotiation.offer_fakes import (
    NOW,
    STL,
    USER,
    FakeAudit,
    FakeMailer,
    FakeNotifier,
    FakeOwnership,
    FakeProducts,
    FakeSettings,
    FakeStore,
    make_offer,
)

ADMIN_ID = uuid.uuid4()
ADMIN = Responder(OfferActor.ADMIN, ADMIN_ID)
CUSTOMER = Responder(OfferActor.CUSTOMER, USER)


@dataclass
class World:
    store: FakeStore = field(default_factory=FakeStore)
    products: FakeProducts = field(default_factory=lambda: FakeProducts({STL.id: STL}))
    ownership: FakeOwnership = field(default_factory=FakeOwnership)
    notifier: FakeNotifier = field(default_factory=FakeNotifier)
    mailer: FakeMailer = field(default_factory=FakeMailer)
    audit: FakeAudit = field(default_factory=FakeAudit)
    now: datetime = NOW

    @property
    def deps(self) -> OfferDeps:
        return OfferDeps(
            offers=self.store,
            products=self.products,
            ownership=self.ownership,
            settings=FakeSettings(),
            notifier=self.notifier,
            mailer=self.mailer,
            audit=self.audit,
            clock=lambda: self.now,
        )

    def seed(self, **over: Any) -> Offer:
        offer = make_offer(**over)
        self.store.offers[offer.id] = offer
        return offer

    def customer_turn(self, **over: Any) -> Offer:
        return self.seed(status=OfferStatus.AWAITING_CUSTOMER, turn=OfferTurn.CUSTOMER, **over)

    def untouched(self, offer: Offer) -> bool:
        return (
            self.store.offers[offer.id] == offer
            and not self.store.rounds_by_offer.get(offer.id)
            and not (self.audit.rows or self.notifier.sent or self.mailer.sent)
        )


async def test_admin_counter_emails_and_notifies_the_customer() -> None:
    world = World()
    offer = world.seed()
    await counter_offer(world.deps, ADMIN, offer_id=offer.id, amount_cents=900, message="hi")
    [round_] = world.store.rounds_by_offer[offer.id]
    assert (round_.actor, round_.action, round_.amount_cents) == (
        OfferActor.ADMIN,
        OfferAction.COUNTERED,
        900,
    )
    [audit] = world.audit.rows
    assert (audit["action"], audit["actor_user_id"]) == ("offer.countered", ADMIN_ID)
    assert audit["after_data"]["status"] == "awaiting_customer"
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"], payload["amount_cents"]) == (
        USER,
        "offer.countered",
        900,
    )
    [(to, template, body)] = world.mailer.sent
    assert (to, template, body["product_name"]) == (USER, COUNTERED_TEMPLATE, STL.name)


async def test_customer_counter_tells_administrators_in_app_only() -> None:
    """SRS 16.1 lists no administrator email."""
    world = World()
    offer = world.customer_turn()
    await counter_offer(world.deps, CUSTOMER, offer_id=offer.id, amount_cents=750, message=None)
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"]) == (None, "offer.countered")
    assert not world.mailer.sent


@pytest.mark.parametrize("who", [ADMIN, CUSTOMER])
async def test_accept_always_emails_the_customer(who: Responder) -> None:
    world = World()
    offer = world.seed() if who is ADMIN else world.customer_turn()
    accepted = await accept_offer(world.deps, who, offer_id=offer.id, expected_amount_cents=800)
    assert accepted.checkout_expires_at == NOW + timedelta(hours=2)
    recipients = [recipient for recipient, _ in world.notifier.sent]
    assert recipients == ([USER] if who is ADMIN else [None, USER])
    assert all(p["agreed_amount_cents"] == 800 for _, p in world.notifier.sent)
    [(to, template, body)] = world.mailer.sent
    assert (to, template) == (USER, ACCEPTED_TEMPLATE)
    assert body["checkout_expires_at"] == accepted.checkout_expires_at.isoformat()
    assert world.store.offers[offer.id].status is OfferStatus.ACCEPTED


async def test_accept_uses_todays_lowered_list_price() -> None:
    world = World(products=FakeProducts({STL.id: replace(STL, price_cents=650)}))
    offer = world.seed()
    accepted = await accept_offer(world.deps, ADMIN, offer_id=offer.id, expected_amount_cents=800)
    assert accepted.agreed_amount_cents == 650
    assert world.store.rounds_by_offer[offer.id][0].amount_cents == 650


async def test_reject_emails_the_customer_with_the_cooldown() -> None:
    world = World()
    offer = world.seed()
    rejected = await reject_offer(world.deps, ADMIN, offer_id=offer.id, reason="no")
    assert rejected.cooldown_until == NOW + timedelta(minutes=10)
    [(_, template, body)] = world.mailer.sent
    assert (template, body["cooldown_until"]) == (
        REJECTED_TEMPLATE,
        (NOW + timedelta(minutes=10)).isoformat(),
    )
    assert world.store.rounds_by_offer[offer.id][0].message == "no"


async def test_withdraw_tells_administrators_and_sends_no_email() -> None:
    world = World()
    offer = world.seed()
    await withdraw_offer(world.deps, CUSTOMER, offer_id=offer.id, reason=None)
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"]) == (None, "offer.withdrawn")
    assert not world.mailer.sent
    assert world.store.offers[offer.id].status is OfferStatus.WITHDRAWN


async def test_a_customer_never_reaches_anothers_offer() -> None:
    world = World()
    offer = world.seed(user_id=uuid.uuid4())
    with pytest.raises(OfferNotFoundError):
        await withdraw_offer(world.deps, CUSTOMER, offer_id=offer.id, reason=None)
    assert world.untouched(offer)


@pytest.mark.parametrize("who", [ADMIN, CUSTOMER])
async def test_a_stale_accept_writes_nothing(who: Responder) -> None:
    """ADR-035 d9: checked before the product and ownership, so it is what a stale page sees."""
    world = World(ownership=FakeOwnership(owned=True), products=FakeProducts({}))
    offer = world.seed() if who is ADMIN else world.customer_turn()
    with pytest.raises(OfferAmountChangedError):
        await accept_offer(world.deps, who, offer_id=offer.id, expected_amount_cents=850)
    assert world.untouched(offer)


async def test_accept_refuses_an_stl_owned_meanwhile() -> None:
    world = World(ownership=FakeOwnership(owned=True))
    offer = world.seed()
    with pytest.raises(OfferProductOwnedError):
        await accept_offer(world.deps, ADMIN, offer_id=offer.id, expected_amount_cents=800)
    assert world.untouched(offer)


@pytest.mark.parametrize(
    "product", [None, replace(STL, listed=False), replace(STL, is_available=False)]
)
async def test_counter_and_accept_recheck_the_product(product: CartProduct | None) -> None:
    world = World(products=FakeProducts({STL.id: product} if product else {}))
    offer = world.seed()
    with pytest.raises(OfferNotAllowedError):
        await accept_offer(world.deps, ADMIN, offer_id=offer.id, expected_amount_cents=800)
    with pytest.raises(OfferNotAllowedError):
        await counter_offer(world.deps, ADMIN, offer_id=offer.id, amount_cents=900, message=None)
    assert world.untouched(offer)


async def test_reject_and_withdraw_work_on_a_hidden_product() -> None:
    world = World(products=FakeProducts({}))
    rejected = await reject_offer(world.deps, ADMIN, offer_id=world.seed().id, reason=None)
    withdrawn = await withdraw_offer(world.deps, CUSTOMER, offer_id=world.seed().id, reason=None)
    assert (rejected.status, withdrawn.status) == (OfferStatus.REJECTED, OfferStatus.WITHDRAWN)


async def test_out_of_turn_writes_nothing() -> None:
    world = World()
    offer = world.seed()
    with pytest.raises(OfferNotYourTurnError):
        await counter_offer(world.deps, CUSTOMER, offer_id=offer.id, amount_cents=900, message=None)
    assert world.untouched(offer)


def _accepted(world: World, expires_at: Any) -> Offer:
    return world.seed(
        status=OfferStatus.ACCEPTED,
        turn=None,
        responds_by=None,
        agreed_amount_cents=800,
        accepted_at=NOW - timedelta(hours=1),
        checkout_expires_at=expires_at,
    )


async def test_checkout_expiry_closes_once_and_tells_the_customer_in_app() -> None:
    world = World()
    offer = _accepted(world, NOW)
    for _ in range(2):
        await expire_checkout_offer(
            world.store, world.notifier, world.audit, offer_id=offer.id, now=NOW
        )
    assert world.store.offers[offer.id].status is OfferStatus.CHECKOUT_EXPIRED
    assert len(world.store.rounds_by_offer[offer.id]) == 1
    [audit] = world.audit.rows
    assert (audit["action"], audit["actor_user_id"]) == ("offer.checkout_expired", None)
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"]) == (USER, "offer.checkout_expired")


async def test_checkout_expiry_skips_an_open_window_or_a_locked_row() -> None:
    world = World()
    early = _accepted(world, NOW + timedelta(seconds=1))
    locked = _accepted(world, NOW)
    world.store.locked_elsewhere.add(locked.id)
    for offer in (early, locked):
        assert not await expire_checkout_offer(
            world.store, world.notifier, world.audit, offer_id=offer.id, now=NOW
        )
    assert not world.audit.rows and not world.notifier.sent


async def _remind(world: World, offer: Offer, at: Any = NOW) -> bool:
    return await remind_offer(
        world.store, world.products, world.notifier, world.mailer, offer_id=offer.id, now=at
    )


async def test_reminder_is_sent_once_per_turn() -> None:
    world = World()
    offer = world.customer_turn(remind_at=NOW)
    assert await _remind(world, offer)
    assert not await _remind(world, offer)
    [(to, template, body)] = world.mailer.sent
    assert (to, template, body["responds_by"]) == (
        USER,
        EXPIRING_SOON_TEMPLATE,
        offer.responds_by and offer.responds_by.isoformat(),
    )
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"]) == (USER, "offer.expiring_soon")
    assert world.store.offers[offer.id].remind_at is None
    assert world.store.offers[offer.id].updated_at == offer.updated_at


async def test_reminder_not_yet_due_is_kept() -> None:
    world = World()
    offer = world.customer_turn(remind_at=NOW + timedelta(seconds=1))
    assert not await _remind(world, offer)
    assert world.store.offers[offer.id].remind_at == offer.remind_at


async def test_a_reminder_past_the_deadline_is_dropped_unsent() -> None:
    world = World()
    offer = world.customer_turn(remind_at=NOW - timedelta(hours=1), responds_by=NOW)
    assert not await _remind(world, offer)
    assert world.store.offers[offer.id].remind_at is None
    assert not world.mailer.sent and not world.notifier.sent


async def test_the_deadline_is_read_after_the_lock_is_taken() -> None:
    """A wait on the row lock that outlasts the deadline is 410, never a late answer."""
    world = World()

    @dataclass
    class SlowLock(FakeStore):
        async def lock(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
            world.now = NOW + timedelta(seconds=1)
            return await super().lock(offer_id, user_id=user_id)

    world.store = SlowLock()
    offer = world.seed(responds_by=NOW + timedelta(seconds=1))
    with pytest.raises(OfferExpiredError):
        await accept_offer(world.deps, ADMIN, offer_id=offer.id, expected_amount_cents=800)
    assert world.untouched(offer)


@pytest.mark.parametrize(
    ("who", "call"),
    [
        (CUSTOMER, "reject"),
        (ADMIN, "withdraw"),
    ],
)
async def test_a_party_cannot_make_the_others_move(who: Responder, call: str) -> None:
    """The routes never wire these, and the service refuses them anyway."""
    world = World()
    offer = world.seed()
    action = reject_offer if call == "reject" else withdraw_offer
    with pytest.raises(OfferInvalidTransitionError):
        await action(world.deps, who, offer_id=offer.id, reason=None)
    assert world.untouched(offer)
