"""Negotiation's ports. The application layer depends on these, never on infrastructure.
Products come through Catalog's `CartProductReader`; audit rows through Platform's port."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.catalog.application.ports import CartProductReader as CartProductReader
from app.negotiation.domain.enums import OfferStatus
from app.negotiation.domain.offers import NewOffer, NewRound, Offer, OfferRound
from app.platform.application.ports import AuditWriter as AuditWriter

# (rank, sort_at, id): the admin queue's keyset (ADR-034).
QueueKey = tuple[int, datetime, UUID]


@dataclass(frozen=True)
class CustomerOfferFilters:
    status: OfferStatus | None = None
    product_id: UUID | None = None


@dataclass(frozen=True)
class AdminOfferFilters:
    status: OfferStatus | None = None
    product_id: UUID | None = None
    user_id: UUID | None = None
    responds_before: datetime | None = None


@dataclass(frozen=True)
class QueuedOffer:
    offer: Offer
    key: QueueKey


class OfferStore(Protocol):
    async def add(self, offer: NewOffer, *, at: datetime) -> Offer:
        """Offer and first round in a SAVEPOINT; `uq_offers_live` -> OfferAlreadyActiveError."""
        ...

    async def cooldowns(self, user_id: UUID, product_id: UUID) -> list[datetime]:
        """`cooldown_until` of every rejected offer for this customer and product."""
        ...

    async def get(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        """No lock. With `user_id`, only that customer's offer (else None)."""
        ...

    async def rounds(self, offer_id: UUID) -> list[OfferRound]:
        """In `sequence` order."""
        ...

    async def customer_page(
        self,
        user_id: UUID,
        filters: CustomerOfferFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[Offer]:
        """Newest first, by (created_at, id)."""
        ...

    async def queue_page(
        self, filters: AdminOfferFilters, *, after: QueueKey | None, limit: int
    ) -> list[QueuedOffer]: ...

    async def overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        """Awaiting offers with `responds_by <= now`, soonest first. Takes no lock."""
        ...

    async def checkout_overdue_ids(self, now: datetime, limit: int) -> list[UUID]:
        """Accepted offers with `checkout_expires_at <= now`, soonest first. No lock."""
        ...

    async def reminder_due_ids(self, now: datetime, limit: int) -> list[UUID]:
        """Offers with `remind_at <= now`, soonest first. No lock."""
        ...

    async def lock(self, offer_id: UUID, *, user_id: UUID | None = None) -> Offer | None:
        """`FOR UPDATE`, waiting for a racing action or expiry; `user_id` scopes as `get`."""
        ...

    async def lock_unless_locked(self, offer_id: UUID) -> Offer | None:
        """`FOR UPDATE SKIP LOCKED`: None if absent or another transaction holds it."""
        ...

    async def save_state(self, offer: Offer) -> None:
        """Writes every mutable column (never `initial_amount_cents`); caller holds the lock."""
        ...

    async def add_round(self, offer_id: UUID, new: NewRound, *, at: datetime) -> None: ...

    async def next_sequence(self, offer_id: UUID) -> int: ...

    async def lock_acquisition(self, user_id: UUID, product_id: UUID) -> None:
        """Transaction-scoped advisory lock on (user, product): submission and the STL
        purchase's auto-close serialise on it (ADR-037)."""
        ...

    async def lock_live(self, user_id: UUID, product_id: UUID) -> list[Offer]:
        """Live offers for (user, product), `FOR UPDATE` in id order (at most one)."""
        ...


class PaymentInFlight(Protocol):
    async def in_flight(self, offer_id: UUID) -> bool:
        """A pending or processing attempt on an uncancelled order holding the offer's line."""
        ...


class StlOwnership(Protocol):
    async def owns(self, user_id: UUID, product_id: UUID) -> bool:
        """A paid, unrefunded STL line (ADR-019 d5)."""
        ...


class OfferSettings(Protocol):
    """The slice of Platform's `SettingsReader` offers need, read in the caller's snapshot."""

    async def get_bool(self, key: str) -> bool: ...

    async def get_int(self, key: str) -> int: ...

    async def get_duration_seconds(self, key: str) -> int: ...


class OfferNotifier(Protocol):
    """In-app notifications, written in the caller's transaction (notification contract)."""

    async def notify_administrators(self, payload: dict[str, Any]) -> None: ...

    async def notify_customer(self, user_id: UUID, payload: dict[str, Any]) -> None: ...


class OfferMailer(Protocol):
    """Customer email through Platform's outbox, in the caller's transaction (ADR-011)."""

    async def send(self, user_id: UUID, template: str, payload: dict[str, Any]) -> None: ...


class CustomerDirectory(Protocol):
    async def emails(self, user_ids: list[UUID]) -> dict[UUID, str]: ...
