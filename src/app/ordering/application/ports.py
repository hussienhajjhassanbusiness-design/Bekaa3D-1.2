"""Ordering's repository ports. Every method that writes `cart_items` is called only
while the caller holds `CartStore.lock` on that cart (VS-022 plan §3.3 invariant)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, overload
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.entities import Cart, CartLine
from app.ordering.domain.enums import OrderItemStatus as OrderItemStatus  # re-exported (VS-030)
from app.ordering.domain.enums import OrderStatus
from app.ordering.domain.order_status import NO_REFUNDS as NO_REFUNDS  # re-exported (VS-030)
from app.ordering.domain.order_status import RefundFacts as RefundFacts  # re-exported (VS-030)
from app.ordering.domain.orders import (
    CustomerOrder,
    CustomerOrderLine,
    HistoryEntry,
    NewOrder,
    NewOrderLine,
    Order,
    OrderLine,
    StatusChange,
)


class CartStore(Protocol):
    @overload
    async def lock(self, user_id: UUID, *, create: Literal[True]) -> Cart: ...

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[False]) -> Cart | None: ...

    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        """Row-lock the user's cart (`FOR UPDATE`), creating it first if `create`;
        None only when `create` is False and no cart exists."""
        ...

    async def get(self, user_id: UUID) -> Cart | None:
        """No lock: reads only."""
        ...

    async def lines(self, cart_id: UUID) -> list[CartLine]:
        """Ordered by (created_at, id)."""
        ...

    async def line(self, cart_id: UUID, product_id: UUID) -> CartLine | None: ...

    async def count_lines(self, cart_id: UUID) -> int: ...

    async def insert_line(
        self,
        *,
        cart_id: UUID,
        product_id: UUID,
        product_type: ProductType,
        quantity: int,
        price_snapshot_cents: int,
        currency: str,
    ) -> CartLine: ...

    async def set_quantity(self, line_id: UUID, quantity: int) -> CartLine: ...

    async def delete_line(self, cart_id: UUID, product_id: UUID) -> bool: ...

    async def clear(self, cart_id: UUID) -> int: ...

    async def touch(self, cart_id: UUID) -> None:
        """`updated_at = now()` on the cart."""
        ...


@dataclass(frozen=True)
class PaymentAttemptRef:
    """One payment attempt as Ordering sees it; Payments owns the row."""

    id: UUID
    provider: str
    status: str
    amount_cents: int
    currency: str
    # Never logged or audited (VS-024 2.1).
    redirect_url: str | None = field(default=None, repr=False)


class PaymentAttempts(Protocol):
    """Implemented by Payments (`app.payments.public`); checkout never imports Payments."""

    def configured_providers(self) -> frozenset[str]: ...

    async def live_attempt(self, order_id: UUID) -> PaymentAttemptRef | None:
        """The `pending` or `processing` attempt, with its `redirect_url`. No lock."""
        ...

    async def previous_provider(self, order_id: UUID) -> str | None:
        """The provider of the order's latest attempt. No lock."""
        ...

    async def open_attempt(
        self, *, order_id: UUID, amount_cents: int, currency: str, provider: str, at: datetime
    ) -> PaymentAttemptRef: ...

    async def open_retry_attempt(
        self, *, order_id: UUID, amount_cents: int, currency: str, provider: str, at: datetime
    ) -> PaymentAttemptRef:
        """The INSERT in a SAVEPOINT; `uq_payments_one_live` raises LiveAttemptExistsError,
        any other integrity error propagates (VS-024 2.1)."""
        ...


@dataclass(frozen=True)
class AcceptedOffer:
    """An accepted offer as checkout sees it; Negotiation owns the row (VS-041)."""

    id: UUID
    product_id: UUID
    agreed_amount_cents: int
    currency: str
    checkout_expires_at: datetime


class OfferCheckouts(Protocol):
    """Implemented by Negotiation (`app.negotiation.public`). Both raise
    OfferCheckoutNotFoundError, OfferCheckoutExpiredError or OfferNotCheckoutableError."""

    async def read(self, offer_id: UUID, user_id: UUID, *, now: datetime) -> AcceptedOffer:
        """No lock: refusals before any insert."""
        ...

    async def lock(
        self, offer_id: UUID, user_id: UUID, *, clock: Callable[[], datetime]
    ) -> AcceptedOffer:
        """`FOR UPDATE`, then re-checked with `clock()` read after the lock (ADR-037)."""
        ...


class SettingsSource(Protocol):
    """The slice of Platform's `SettingsReader` checkout needs."""

    async def get_bool(self, key: str) -> bool: ...

    async def get_int(self, key: str) -> int: ...

    async def get_money_cents(self, key: str) -> int: ...

    async def get_text(self, key: str) -> str | None: ...


@dataclass(frozen=True)
class CheckoutAddressSnapshot:
    """What an order copies from the customer's address; the phone is E.164."""

    recipient_name: str
    phone: str
    governorate: str
    city: str
    area: str | None
    street: str | None
    landmark_notes: str


class CheckoutAddresses(Protocol):
    """Implemented over `app.identity.public.lock_checkout_address`."""

    async def lock_for_share(
        self, address_id: UUID, user_id: UUID
    ) -> CheckoutAddressSnapshot | None:
        """`FOR SHARE`; None for an unknown, foreign or deleted address alike."""
        ...


class CashChecks(Protocol):
    """Cash eligibility reads. `lock_phone` comes first and every read follows it."""

    async def lock_phone(self, phone_hash: str) -> None: ...

    async def active_block(self, user_id: UUID, phone_hash: str) -> bool: ...

    async def open_order_count(self, user_id: UUID, phone_hash: str) -> int: ...


class ReceiptOrders(Protocol):
    """VS-029b's slice of the order store, in the ADR-024 lock order."""

    async def lock_owned_order(self, order_id: UUID, user_id: UUID) -> Order | None: ...

    async def lock_lines(self, order_id: UUID) -> list[OrderLine]: ...

    async def stamp_receipt_confirmed(
        self, order_id: UUID, line_ids: Sequence[UUID], *, at: datetime
    ) -> list[UUID]:
        """Only where unset, so the first confirmation stays; returns the ids it set."""
        ...

    async def stamp_problem_reported(
        self, order_id: UUID, line_ids: Sequence[UUID], *, at: datetime
    ) -> list[UUID]:
        """Only where unset, so the first report's time stays; returns the ids it set."""
        ...


class ProblemReportInbox(Protocol):
    """Implemented over `app.engagement.public.submit_problem_report`; returns the message id."""

    async def submit(
        self,
        *,
        user_id: UUID,
        order_id: UUID,
        order_number: str,
        recipient_name: str | None,
        email: str,
        message: str,
    ) -> UUID: ...


class OrderNotices(Protocol):
    async def cash_order_placed(self, order: Order, lines: Sequence[OrderLine]) -> None: ...


class OrderStore(Protocol):
    """Ordering's order repository. Locks follow ADR-024: `orders`, then lines by id."""

    async def insert_order(self, order: NewOrder, number: Callable[[], str]) -> Order:
        """Insert in a SAVEPOINT, regenerating the number on a collision (5 attempts)."""
        ...

    async def insert_lines(
        self,
        order: Order,
        lines: Sequence[NewOrderLine],
        *,
        status: OrderItemStatus,
    ) -> list[OrderLine]:
        """In a SAVEPOINT; the STL ownership index maps to ProductAlreadyOwnedError."""
        ...

    async def add_history(self, changes: Sequence[StatusChange]) -> None: ...

    async def owned_stl_product_ids(self, user_id: UUID, product_ids: Sequence[UUID]) -> set[UUID]:
        """Paid, unrefunded STL lines: `awaiting_delivery` or `delivered` (ADR-019 d5)."""
        ...

    async def order_number(self, order_id: UUID) -> str | None: ...

    async def unpaid_offer_order(self, offer_id: UUID) -> UUID | None:
        """The uncancelled order whose line still awaits payment for this offer. No lock."""
        ...

    async def lock_order(self, order_id: UUID) -> Order | None:
        """`SELECT ... FROM orders WHERE id = :id FOR UPDATE`."""
        ...

    async def lock_lines(self, order_id: UUID) -> list[OrderLine]:
        """`SELECT ... FROM order_items WHERE order_id = :id ORDER BY id FOR UPDATE`."""
        ...

    async def lock_owned_order(self, order_id: UUID, user_id: UUID) -> Order | None:
        """`orders` FOR UPDATE with the ownership predicate (VS-024 2.1)."""
        ...

    async def order_lines(self, order_id: UUID) -> list[OrderLine]:
        """The order's lines by id, no lock (the retry holds the orders row)."""
        ...

    async def set_line_status(
        self, line_ids: Sequence[UUID], status: OrderItemStatus, *, at: datetime
    ) -> None: ...

    async def set_order_status(
        self, order_id: UUID, status: OrderStatus, *, at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class OrderPaymentView:
    """`shown`: the live or paid attempt, else the latest one (VS-025 plan Q4)."""

    reached_paid: bool
    shown: PaymentAttemptRef | None
    latest_initiated_at: datetime | None = None


class OrderPaymentReader(Protocol):
    """Implemented by Payments (`app.payments.public`); an order with no payment is absent."""

    async def views(self, order_ids: Sequence[UUID]) -> dict[UUID, OrderPaymentView]: ...


@dataclass(frozen=True)
class OrderFilters:
    status: OrderStatus | None = None
    placed_after: datetime | None = None
    placed_before: datetime | None = None


class OrderHistoryStore(Protocol):
    """The customer's own orders; every query carries `user_id` in its predicate."""

    async def page(
        self,
        user_id: UUID,
        filters: OrderFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[CustomerOrder]:
        """`placed_after` inclusive, `placed_before` exclusive; `(placed_at, id)` DESC."""
        ...

    async def get(self, user_id: UUID, order_id: UUID) -> CustomerOrder | None: ...

    async def lines(self, user_id: UUID, order_id: UUID) -> list[CustomerOrderLine]: ...

    async def history(self, user_id: UUID, order_id: UUID) -> list[HistoryEntry]:
        """Oldest first."""
        ...
