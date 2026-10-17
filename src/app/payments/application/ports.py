"""Payments' ports (VS-023 plan 3.6): the provider adapter and the payment repository.
A provider call never runs inside a transaction or under a lock (ADR-024 d9)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.ordering.public import LockedOrder
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.outcome import ProviderResult
from app.payments.domain.payments import Payment


@dataclass(frozen=True)
class CreatePayment:
    """`payment_id` is our merchant reference: every provider event echoes it."""

    payment_id: UUID
    order_number: str
    amount_cents: int
    currency: str
    return_url: str


@dataclass(frozen=True)
class CreatedPayment:
    provider_payment_id: str
    redirect_url: str | None


@dataclass(frozen=True)
class PaymentRef:
    payment_id: UUID
    provider_payment_id: str | None


@dataclass(frozen=True)
class ProviderStatus:
    """The provider's answer, and its own id for the payment when it has one."""

    result: ProviderResult
    provider_payment_id: str | None


@dataclass(frozen=True)
class ParsedEvent:
    event_id: str
    event_type: str | None
    payment_reference: UUID | None
    provider_payment_id: str | None
    payload: dict[str, Any]


class PaymentProviderPort(Protocol):
    name: str
    supports_status_query: bool
    # False: events are stored unverified, on the per-IP bucket (plan 2.2 step 4).
    signs_webhooks: bool

    async def create_payment(self, request: CreatePayment) -> CreatedPayment:
        """Raises ProviderUnavailableError when the outcome is unknown."""
        ...

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        """By merchant reference; works without `provider_payment_id` (plan R3)."""
        ...

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> ParsedEvent:
        """Raises InvalidSignatureError, then MalformedEventError."""
        ...

    async def aclose(self) -> None: ...


class PaymentStore(Protocol):
    """Payments' repository. `lock` is taken only after the order's locks (ADR-024 d9)."""

    async def insert_pending(
        self,
        *,
        order_id: UUID,
        provider: PaymentProvider,
        amount_cents: int,
        currency: str,
        at: datetime,
    ) -> Payment: ...

    async def get(self, payment_id: UUID) -> Payment | None:
        """No lock."""
        ...

    async def lock(self, payment_id: UUID) -> Payment | None:
        """`SELECT ... FROM payments WHERE id = :id FOR UPDATE`."""
        ...

    async def find_by_reference(
        self, provider: PaymentProvider, provider_payment_id: str
    ) -> Payment | None: ...

    async def set_provider_reference(
        self, payment_id: UUID, provider_payment_id: str, *, redirect_url: str | None, at: datetime
    ) -> None: ...

    async def mark_failed(self, payment_id: UUID, *, at: datetime) -> None: ...

    async def mark_paid(self, payment_id: UUID, *, at: datetime) -> None: ...

    async def mark_status(self, payment_id: UUID, status: PaymentStatus, *, at: datetime) -> None:
        """`processing`, `failed` or `expired`, with its timestamp."""
        ...

    async def mark_late_capture(self, payment_id: UUID, *, at: datetime, fail: bool) -> None:
        """`late_captured_at`, once; `fail` also ends a live attempt."""
        ...

    async def fill_provider_reference(
        self, payment_id: UUID, provider_payment_id: str, *, at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class NewWebhookEvent:
    """Stored processed with `processing_error` when ignored (unknown payment...)."""

    provider: PaymentProvider
    provider_event_id: str
    event_type: str | None
    payload: dict[str, Any]
    signature_valid: bool
    provider_payment_id: str | None
    payment_id: UUID | None
    processing_error: str | None
    processed_at: datetime | None


@dataclass(frozen=True)
class WebhookEvent:
    id: UUID
    provider: PaymentProvider
    payment_id: UUID | None
    processed_at: datetime | None


class WebhookEventStore(Protocol):
    async def insert_if_new(self, event: NewWebhookEvent) -> UUID | None: ...

    async def get(self, event_id: UUID) -> WebhookEvent | None: ...

    async def unprocessed_ids(self, limit: int) -> list[UUID]: ...

    async def mark_processed(self, event_id: UUID, *, at: datetime) -> None: ...

    async def record_error(self, event_id: UUID, error: str) -> None: ...


class OrderSide(Protocol):
    """Ordering's half of a payment apply, through `ordering.public` (plan 3.0)."""

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        """`orders` FOR UPDATE, then its lines FOR UPDATE ORDER BY id."""
        ...

    async def mark_paid(self, locked: LockedOrder, *, at: datetime) -> tuple[UUID, ...]:
        """The STL lines moved to `awaiting_delivery`."""
        ...

    async def recompute_unpaid(self, locked: LockedOrder) -> None: ...


class PaymentNotices(Protocol):
    async def payment_confirmed(self, locked: LockedOrder) -> None: ...
