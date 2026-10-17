"""Payments' ports (VS-023 plan 3.6): the provider adapter and the payment repository.
A provider call never runs inside a transaction or under a lock (ADR-024 d9)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.payments.domain.enums import PaymentProvider
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
