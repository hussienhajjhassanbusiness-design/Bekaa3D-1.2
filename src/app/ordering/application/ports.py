"""Ordering's repository ports. Every method that writes `cart_items` is called only
while the caller holds `CartStore.lock` on that cart (VS-022 plan §3.3 invariant)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, overload
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.entities import Cart, CartLine
from app.ordering.domain.enums import OrderItemStatus, OrderStatus
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
    """The pending payment checkout opened; Payments owns the row."""

    id: UUID
    provider: str
    status: str
    amount_cents: int
    currency: str


class PaymentAttempts(Protocol):
    """Implemented by Payments (`app.payments.public`); checkout never imports Payments."""

    def configured_providers(self) -> frozenset[str]: ...

    async def open_attempt(
        self, *, order_id: UUID, amount_cents: int, currency: str, provider: str, at: datetime
    ) -> PaymentAttemptRef: ...


class SettingsSource(Protocol):
    """The slice of Platform's `SettingsReader` checkout needs."""

    async def get_bool(self, key: str) -> bool: ...


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

    async def lock_order(self, order_id: UUID) -> Order | None:
        """`SELECT ... FROM orders WHERE id = :id FOR UPDATE`."""
        ...

    async def lock_lines(self, order_id: UUID) -> list[OrderLine]:
        """`SELECT ... FROM order_items WHERE order_id = :id ORDER BY id FOR UPDATE`."""
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
