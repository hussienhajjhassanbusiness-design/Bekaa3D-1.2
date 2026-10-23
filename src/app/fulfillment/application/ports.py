"""What Fulfillment's use cases need from Ordering, Payments and the notices adapter."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.ordering.public import (
    AdminHistoryEntry,
    AdminOrder,
    AdminOrderLine,
    LockedOrder,
    OrderItemStatus,
    OrderLine,
    OrderStatus,
)
from app.payments.public import OrderPaymentRow


class DeliveryOrders(Protocol):
    async def lock(self, order_id: UUID) -> LockedOrder | None:
        """`orders` FOR UPDATE, then its lines by id (ADR-024 d9)."""
        ...

    async def mark_delivered(
        self, locked: LockedOrder, *, line_id: UUID, admin_id: UUID, at: datetime
    ) -> tuple[OrderLine, OrderStatus]: ...


class FulfillmentOrders(DeliveryOrders, Protocol):
    async def transition(
        self,
        locked: LockedOrder,
        *,
        line_id: UUID,
        target: OrderItemStatus,
        admin_id: UUID,
        at: datetime,
        reached_paid: bool,
        note: str | None,
    ) -> tuple[OrderLine, OrderStatus]: ...

    async def hand_over(
        self, locked: LockedOrder, *, admin_id: UUID, at: datetime, note: str | None
    ) -> tuple[tuple[OrderLine, ...], OrderStatus]: ...


class OrderPayments(Protocol):
    async def reached_paid(self, order_id: UUID) -> bool:
        """`paid`, `partially_refunded` or `refunded`; read under the orders lock (BR-148)."""
        ...

    async def record_cash(
        self, *, order_id: UUID, amount_cents: int, currency: str, admin_id: UUID, at: datetime
    ) -> UUID:
        """The order's one cash payment; raises CashAlreadyRecordedError on a second."""
        ...

    async def rows(self, order_id: UUID) -> list[OrderPaymentRow]: ...


class AdminOrderReads(Protocol):
    async def get(self, order_id: UUID) -> AdminOrder | None: ...

    async def lines(self, order_id: UUID) -> list[AdminOrderLine]: ...

    async def history(self, order_id: UUID) -> list[AdminHistoryEntry]: ...


class DeliveryNotices(Protocol):
    async def stl_delivered(self, locked: LockedOrder, line: OrderLine) -> None:
        """The customer's outbox email and in-app notification, on the caller's session."""
        ...


class FulfillmentNotices(DeliveryNotices, Protocol):
    async def step_reached(self, locked: LockedOrder, step: OrderItemStatus) -> None:
        """One email and one notification for the whole order (ADR-040 d2)."""
        ...

    async def cash_handed_over(
        self, locked: LockedOrder, *, payment_id: UUID, amount_cents: int, recorded_at: datetime
    ) -> None:
        """The delivered / picked-up email with the cash receipt, and its notification."""
        ...
