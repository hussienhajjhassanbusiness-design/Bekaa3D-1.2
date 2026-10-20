"""`submit_offer` and `expire_offer` (VS-039) over in-memory fakes: check order, and that a
refusal writes nothing."""

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from app.catalog.application.ports import ProductType
from app.catalog.domain.enums import PurchaseMode
from app.negotiation.application.services.expire_offers import expire_offer
from app.negotiation.application.services.submit_offer import OfferRequestContext, submit_offer
from app.negotiation.domain.enums import OfferAction, OfferActor, OfferStatus, OfferTurn
from app.negotiation.domain.exceptions import (
    OfferBelowMinimumError,
    OfferCooldownActiveError,
    OfferNotAllowedError,
    OfferProductOwnedError,
    OffersPausedError,
)
from app.negotiation.domain.offers import Offer
from tests.unit.negotiation.offer_fakes import (
    NOW,
    STL,
    USER,
    FakeAudit,
    FakeNotifier,
    FakeOwnership,
    FakeProducts,
    FakeSettings,
    FakeStore,
)


@dataclass
class World:
    store: FakeStore = field(default_factory=FakeStore)
    products: FakeProducts = field(default_factory=lambda: FakeProducts({STL.id: STL}))
    ownership: FakeOwnership = field(default_factory=FakeOwnership)
    settings: FakeSettings = field(default_factory=FakeSettings)
    notifier: FakeNotifier = field(default_factory=FakeNotifier)
    audit: FakeAudit = field(default_factory=FakeAudit)

    async def submit(self, product_id: UUID = STL.id, amount: int = 800) -> Offer:
        return await submit_offer(
            offers=self.store,
            products=self.products,
            ownership=self.ownership,
            settings=self.settings,
            notifier=self.notifier,
            audit=self.audit,
            user_id=USER,
            product_id=product_id,
            amount_cents=amount,
            message=None,
            now=NOW,
            context=OfferRequestContext(request_id="req_1"),
        )

    def wrote_nothing(self) -> bool:
        return not (self.store.offers or self.audit.rows or self.notifier.sent)


async def test_submit_writes_offer_audit_and_admin_notification() -> None:
    world = World()
    offer = await world.submit()
    assert (offer.status, offer.turn) == (OfferStatus.AWAITING_ADMIN, OfferTurn.ADMIN)
    assert offer.responds_by == NOW + timedelta(hours=1)
    [audit] = world.audit.rows
    assert (audit["action"], audit["actor_user_id"], audit["entity_id"]) == (
        "offer.submitted",
        USER,
        offer.id,
    )
    [(recipient, payload)] = world.notifier.sent
    assert recipient is None and payload["event"] == "offer.submitted"


async def test_kill_switch_refuses_before_anything_else() -> None:
    world = World(settings=FakeSettings(accepting=False), ownership=FakeOwnership(owned=True))
    with pytest.raises(OffersPausedError):
        await world.submit(product_id=uuid.uuid4())
    assert world.wrote_nothing()


@pytest.mark.parametrize(
    ("world", "error"),
    [
        (World(products=FakeProducts({})), OfferNotAllowedError),
        (
            World(
                products=FakeProducts(
                    {
                        STL.id: replace(
                            STL, type=ProductType.PHYSICAL, purchase_mode=PurchaseMode.BOTH
                        )
                    }
                )
            ),
            OfferNotAllowedError,
        ),
        (World(ownership=FakeOwnership(owned=True)), OfferProductOwnedError),
    ],
)
async def test_refusals_write_nothing(world: World, error: type[Exception]) -> None:
    with pytest.raises(error):
        await world.submit()
    assert world.wrote_nothing()


async def test_below_floor_writes_nothing() -> None:
    world = World()
    with pytest.raises(OfferBelowMinimumError):
        await world.submit(amount=699)
    assert world.wrote_nothing()


async def test_cooldown_refusal_comes_before_audit_and_notification() -> None:
    """The insert already happened (the transaction rolls it back); nothing else is written."""
    world = World()
    world.store.rejected_cooldowns.append(NOW + timedelta(seconds=1))
    with pytest.raises(OfferCooldownActiveError):
        await world.submit()
    assert not world.audit.rows and not world.notifier.sent


async def _overdue(world: World, *, deadline: datetime) -> Offer:
    offer = await world.submit()
    offer = replace(offer, responds_by=deadline)
    world.store.offers[offer.id] = offer
    world.audit.rows.clear()
    world.notifier.sent.clear()
    return offer


async def _expire(world: World, offer_id: UUID) -> bool:
    return await expire_offer(world.store, world.notifier, world.audit, offer_id=offer_id, now=NOW)


async def test_expire_appends_a_system_round_audits_and_tells_the_customer() -> None:
    world = World()
    offer = await _overdue(world, deadline=NOW)
    assert await _expire(world, offer.id)
    assert world.store.offers[offer.id].status is OfferStatus.EXPIRED
    last = world.store.rounds_by_offer[offer.id][-1]
    assert (last.sequence, last.actor, last.action) == (2, OfferActor.SYSTEM, OfferAction.EXPIRED)
    [audit] = world.audit.rows
    assert (audit["action"], audit["actor_user_id"]) == ("offer.expired", None)
    [(recipient, payload)] = world.notifier.sent
    assert (recipient, payload["event"]) == (USER, "offer.expired")


async def test_expire_twice_is_a_noop() -> None:
    world = World()
    offer = await _overdue(world, deadline=NOW)
    assert await _expire(world, offer.id)
    assert not await _expire(world, offer.id)
    assert len(world.store.rounds_by_offer[offer.id]) == 2
    assert len(world.audit.rows) == 1


async def test_expire_skips_an_offer_locked_elsewhere_or_not_yet_due() -> None:
    world = World()
    locked = await _overdue(world, deadline=NOW)
    world.store.locked_elsewhere.add(locked.id)
    assert not await _expire(world, locked.id)
    early = await _overdue(world, deadline=NOW + timedelta(seconds=1))
    assert not await _expire(world, early.id)
    assert not world.audit.rows and not world.notifier.sent
