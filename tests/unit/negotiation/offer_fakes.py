"""In-memory fakes of Negotiation's ports, shared by the offer service tests."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.catalog.application.ports import CartProduct, ProductType
from app.negotiation.application.ports import (
    AdminOfferFilters,
    CustomerOfferFilters,
    QueuedOffer,
    QueueKey,
)
from app.negotiation.domain.enums import LIVE_STATUSES, OfferStatus, OfferTurn
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
    acquisition_locks: list[tuple[UUID, UUID]] = field(default_factory=list)

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

    async def checkout_overdue_ids(
        self, now: datetime, limit: int, *, after: tuple[datetime, UUID] | None = None
    ) -> list[tuple[datetime, UUID]]:
        return []

    async def reminder_due_ids(self, now: datetime, limit: int) -> list[UUID]:
        return []

    async def lock(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        offer = self.offers.get(offer_id)
        return offer if offer is not None and user_id in (None, offer.user_id) else None

    async def lock_unless_locked(self, offer_id: UUID) -> Offer | None:
        return None if offer_id in self.locked_elsewhere else self.offers.get(offer_id)

    async def save_state(self, offer: Offer) -> None:
        self.offers[offer.id] = offer

    async def add_round(self, offer_id: UUID, new: NewRound, *, at: datetime) -> None:
        self.rounds_by_offer.setdefault(offer_id, []).append(new)

    async def next_sequence(self, offer_id: UUID) -> int:
        return len(self.rounds_by_offer.get(offer_id, [])) + 1

    async def lock_acquisition(self, user_id: UUID, product_id: UUID) -> None:
        self.acquisition_locks.append((user_id, product_id))

    async def lock_live_for_user(self, user_id: UUID) -> list[Offer]:
        live = (o for o in self.offers.values() if o.status in LIVE_STATUSES)
        return sorted((o for o in live if o.user_id == user_id), key=lambda o: o.id)

    async def lock_live(self, user_id: UUID, product_id: UUID) -> list[Offer]:
        live = (o for o in self.offers.values() if o.status in LIVE_STATUSES)
        return sorted(
            (o for o in live if (o.user_id, o.product_id) == (user_id, product_id)),
            key=lambda o: o.id,
        )


@dataclass
class FakeInFlight:
    offer_ids: set[UUID] = field(default_factory=set)

    async def in_flight(self, offer_id: UUID) -> bool:
        return offer_id in self.offer_ids


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
        default_factory=lambda: {
            "minimum_offer_percentage": 70,
            "offer_response_window": 3600,
            "offer_checkout_window": 7200,
            "offer_rejection_cooldown": 600,
        }
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
class FakeMailer:
    sent: list[tuple[UUID, str, dict[str, Any]]] = field(default_factory=list)

    async def send(self, user_id: UUID, template: str, payload: dict[str, Any]) -> None:
        self.sent.append((user_id, template, payload))


def make_offer(**over: Any) -> Offer:
    """An `awaiting_admin` offer of 800 on `STL`, due in an hour; override any field."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": USER,
        "product_id": STL.id,
        "status": OfferStatus.AWAITING_ADMIN,
        "turn": OfferTurn.ADMIN,
        "initial_amount_cents": 800,
        "current_amount_cents": 800,
        "agreed_amount_cents": None,
        "currency": "USD",
        "responds_by": NOW + timedelta(hours=1),
        "accepted_at": None,
        "checkout_expires_at": None,
        "rejected_at": None,
        "cooldown_until": None,
        "created_at": NOW - timedelta(hours=1),
        "updated_at": NOW - timedelta(hours=1),
    }
    return Offer(**(fields | over))
