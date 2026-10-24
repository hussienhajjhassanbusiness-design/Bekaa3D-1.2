"""Payments' ports (VS-023 plan 3.6): the provider adapter and the payment repository.
A provider call never runs inside a transaction or under a lock (ADR-024 d9)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.ordering.public import LockedOrder, OrderStatus, RefundFacts
from app.payments.domain.alerts import AlertKind
from app.payments.domain.chargebacks import NewChargeback
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.outcome import ProviderResult
from app.payments.domain.payments import Payment
from app.payments.domain.refunds import ChargebackFact, NewRefund, Refund


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
        """By merchant reference; works without `provider_payment_id` (plan R3). `unknown`
        when the provider has no record of it; never called when `supports_status_query`
        is false (VS-024 3.2a, 3.3)."""
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

    async def mark_paid(
        self,
        payment_id: UUID,
        *,
        at: datetime,
        captured_amount_cents: int | None,
        captured_currency: str | None,
    ) -> None:
        """Status and the provider's captured amount in one UPDATE, under the locks."""
        ...

    async def mark_status(self, payment_id: UUID, status: PaymentStatus, *, at: datetime) -> None:
        """`processing`, `failed` or `expired`, with its timestamp."""
        ...

    async def mark_late_capture(
        self,
        payment_id: UUID,
        *,
        at: datetime,
        fail: bool,
        captured_amount_cents: int | None,
        captured_currency: str | None,
    ) -> None:
        """`late_captured_at` and the captured amount, once; `fail` also ends a live attempt."""
        ...

    async def fill_provider_reference(
        self, payment_id: UUID, provider_payment_id: str, *, at: datetime
    ) -> None: ...

    async def lock_for_order(self, order_id: UUID) -> list[Payment]:
        """Every attempt of the order, FOR UPDATE ORDER BY id; only after the order's locks."""
        ...

    async def live_for_order(self, order_id: UUID) -> Payment | None:
        """The `pending` or `processing` attempt, if any. No lock."""
        ...

    async def previous_provider(self, order_id: UUID) -> PaymentProvider | None:
        """The provider of the order's latest attempt. No lock."""
        ...

    async def stale_live_ids(
        self, *, before: datetime, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[tuple[datetime, UUID]]:
        """Online live attempts initiated at or before `before`, keyset-paged. No lock."""
        ...


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

    async def count_unprocessed_for_payment(self, payment_id: UUID) -> int: ...

    async def mark_processed_for_payment(self, payment_id: UUID, *, at: datetime) -> int: ...


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


class PaymentAlerts(Protocol):
    """Operator alerts, de-duplicated within `dedupe_window` (VS-024 3.5)."""

    async def raise_alert(
        self,
        kind: AlertKind,
        *,
        payment_id: UUID | None,
        order_id: UUID | None,
        details: dict[str, Any],
        dedupe_window: timedelta | None,
    ) -> bool:
        """False when the same alert was already raised within the window."""
        ...


class LateCaptureSink(Protocol):
    """Called in Tx B after a late capture is stored; VS-030 adds the refund (3.6)."""

    async def late_capture_recorded(
        self,
        locked: LockedOrder,
        payment: Payment,
        *,
        captured_amount_cents: int | None,
        captured_currency: str | None,
        reason: str,
        at: datetime,
    ) -> None: ...


class RefundOrders(Protocol):
    """Ordering's half of a refund, through `ordering.public` (VS-030 plan 3.0, 3.4)."""

    async def lock(self, order_id: UUID) -> LockedOrder | None:
        """`orders` FOR UPDATE, then every line FOR UPDATE ORDER BY id (ranks 1-2)."""
        ...

    async def refund_lines(
        self, locked: LockedOrder, line_ids: tuple[UUID, ...], *, actor_user_id: UUID, at: datetime
    ) -> None: ...

    async def chargeback_lines(
        self,
        locked: LockedOrder,
        *,
        refunded: tuple[UUID, ...],
        cancelled: tuple[UUID, ...],
        actor_user_id: UUID,
        at: datetime,
    ) -> None:
        """D4: emptied lines become `refunded` or, unfinished, `cancelled`; no recompute."""
        ...

    async def recompute(
        self,
        locked: LockedOrder,
        *,
        refunded: tuple[UUID, ...],
        refunds: RefundFacts,
        actor_user_id: UUID,
        cancelled: tuple[UUID, ...] = (),
    ) -> OrderStatus:
        """The order status from the locked lines (as moved since the lock) and facts."""
        ...


class RefundStore(Protocol):
    """`refunds` and `refund_items`. Every method but `get` runs under the orders lock."""

    async def get(self, refund_id: UUID) -> Refund | None:
        """Unlocked: only to learn the order id (plan 8.1, note 2)."""
        ...

    async def lock(self, refund_id: UUID) -> Refund | None:
        """`FOR UPDATE` (rank 4)."""
        ...

    async def for_order(self, order_id: UUID) -> list[Refund]:
        """Plain reads; refuses unless this transaction holds the order's row lock."""
        ...

    async def insert(self, new: NewRefund) -> UUID: ...

    async def insert_late_capture(self, new: NewRefund) -> UUID | None:
        """None when the payment already has a live one (`uq_refunds_one_live_late_capture`)."""
        ...

    async def settle(
        self, refund_id: UUID, *, by: UUID, at: datetime, reference: str | None, note: str | None
    ) -> bool:
        """Only from `pending`; False if the row was not pending."""
        ...

    async def fail(self, refund_id: UUID, *, by: UUID, at: datetime, reason: str) -> bool: ...

    async def void(self, refund_id: UUID, *, by: UUID, at: datetime, reason: str) -> bool: ...

    async def mark_reissued(self, refund_id: UUID, *, at: datetime) -> bool: ...

    async def lock_open_for_payment(self, payment_id: UUID) -> list[Refund]:
        """Pending or owed refunds of one payment, `FOR UPDATE ORDER BY id` (rank 4)."""
        ...


class ChargebackStore(Protocol):
    """`chargebacks` and `chargeback_items`. Every method runs under the orders lock."""

    async def for_order(self, order_id: UUID) -> list[ChargebackFact]:
        """Plain reads; refuses unless this transaction holds the order's row lock."""
        ...

    async def dispute_exists(self, provider: PaymentProvider, reference: str) -> bool: ...

    async def insert(self, new: NewChargeback) -> None:
        """Rank 5: waits on `uq_chargebacks_dispute` behind a rival with the same reference."""
        ...


class RefundNotices(Protocol):
    async def refund_issued(
        self, locked: LockedOrder, *, refund_id: UUID, amount_cents: int, currency: str
    ) -> None:
        """The customer's "refund issued" email and `refund` notification (Q7)."""
        ...
