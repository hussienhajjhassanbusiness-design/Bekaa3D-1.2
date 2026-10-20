"""`submit_offer` and `expire_offer` (VS-039) over in-memory fakes: check order, and that a
refusal writes nothing."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from app.catalog.application.ports import CartProduct, ProductType
from app.catalog.domain.enums import PurchaseMode
from app.negotiation.application.ports import (
    AdminOfferFilters,
    CustomerOfferFilters,
    QueuedOffer,
    QueueKey,
)
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
from app.negotiation.domain.offers import NewOffer, NewRound, Offer, OfferRound

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
USER = uuid.uuid4()
STL = CartProduct(
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


@dataclass
class FakeStore:
    offers: dict[UUID, Offer] = field(default_factory=dict)
    rounds_by_offer: dict[UUID, list[NewRound]] = field(default_factory=dict)
    rejected_cooldowns: list[datetime] = field(default_factory=list)
    locked_elsewhere: set[UUID] = field(default_factory=set)

    async def add(self, offer: NewOffer, *, at: datetime) -> Offer:
        row = Offer(
            id=uuid.uuid4(),
            user_id=offer.user_id,
            product_id=offer.product_id,
            status=offer.status,
            turn=offer.turn,
            initial_amount_cents=offer.amount_cents,
            current_amount_cents=offer.amount_cents,
            agreed_amount_cents=None,
            currency=offer.currency,
            responds_by=offer.responds_by,
            accepted_at=None,
            checkout_expires_at=None,
            rejected_at=None,
            cooldown_until=None,
            created_at=at,
            updated_at=at,
        )
        self.offers[row.id] = row
        self.rounds_by_offer[row.id] = [offer.first_round]
        return row

    async def cooldowns(self, user_id: UUID, product_id: UUID) -> list[datetime]:
        return list(self.rejected_cooldowns)

    async def get(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        return self.offers.get(offer_id)

    async def rounds(self, offer_id: UUID) -> list[OfferRound]:
        return []

    async def customer_page(
        self,
        user_id: UUID,
        filters: CustomerOfferFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[Offer]:
        return []

    async def queue_page(
        self, filters: AdminOfferFilters, *, after: QueueKey | None, limit: int
    ) -> list[QueuedOffer]:
        return []

    async def overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        return []

    async def lock_unless_locked(self, offer_id: UUID) -> Offer | None:
        return None if offer_id in self.locked_elsewhere else self.offers.get(offer_id)

    async def save_state(self, offer: Offer) -> None:
        self.offers[offer.id] = offer

    async def add_round(self, offer_id: UUID, new: NewRound, *, at: datetime) -> None:
        self.rounds_by_offer.setdefault(offer_id, []).append(new)

    async def next_sequence(self, offer_id: UUID) -> int:
        return len(self.rounds_by_offer.get(offer_id, [])) + 1


@dataclass
class FakeProducts:
    products: dict[UUID, CartProduct]

    async def get_many(self, product_ids: Sequence[UUID]) -> dict[UUID, CartProduct]:
        return {p: self.products[p] for p in product_ids if p in self.products}


@dataclass
class FakeOwnership:
    owned: bool = False

    async def owns(self, user_id: UUID, product_id: UUID) -> bool:
        return self.owned


@dataclass
class FakeSettings:
    accepting: bool = True
    values: dict[str, int] = field(
        default_factory=lambda: {"minimum_offer_percentage": 70, "offer_response_window": 3600}
    )

    async def get_bool(self, key: str) -> bool:
        assert key == "accepting_orders"
        return self.accepting

    async def get_int(self, key: str) -> int:
        return self.values[key]

    async def get_duration_seconds(self, key: str) -> int:
        return self.values[key]


@dataclass
class FakeNotifier:
    sent: list[tuple[UUID | None, dict[str, Any]]] = field(default_factory=list)

    async def notify_administrators(self, payload: dict[str, Any]) -> None:
        self.sent.append((None, payload))

    async def notify_customer(self, user_id: UUID, payload: dict[str, Any]) -> None:
        self.sent.append((user_id, payload))


@dataclass
class FakeAudit:
    rows: list[dict[str, Any]] = field(default_factory=list)

    async def record(self, **row: Any) -> None:
        self.rows.append(row)


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
