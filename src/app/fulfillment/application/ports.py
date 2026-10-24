"""What Fulfillment's use cases need from Ordering, Payments and the notices adapter."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.ordering.public import (
    AdminHistoryEntry,
    AdminOrder,
    AdminOrderLine,
    CancelReason,
    LineCancel,
    LineState,
    LockedOrder,
    OrderItemStatus,
    OrderLine,
    OrderStatus,
    RefundFacts,
)
from app.payments.public import CancellationRefund, OrderPaymentRow


class DeliveryOrders(Protocol):
    async def lock(self, order_id: UUID) -> LockedOrder | None:
        """`orders` FOR UPDATE, then its lines by id (ADR-024 d9)."""
        ...

    async def mark_delivered(
        self,
        locked: LockedOrder,
        *,
        line_id: UUID,
        admin_id: UUID,
        at: datetime,
        refunds: RefundFacts,
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
        refunds: RefundFacts,
        note: str | None,
    ) -> tuple[OrderLine, OrderStatus]: ...

    async def hand_over(
        self, locked: LockedOrder, *, admin_id: UUID, at: datetime, note: str | None
    ) -> tuple[tuple[OrderLine, ...], OrderStatus]: ...

    async def cancel(
        self,
        locked: LockedOrder,
        cancels: tuple[LineCancel, ...],
        *,
        actor_user_id: UUID,
        at: datetime,
        note: str | None,
        by_customer: bool,
    ) -> None:
        """VS-031's writer: the lines, their reasons and history; no recompute."""
        ...

    async def insert_cash_block(
        self, locked: LockedOrder, *, reason: CancelReason, at: datetime
    ) -> bool:
        """The customer's cart, then the phone lock, then the block (ADR-024 d9)."""
        ...

    async def recompute(
        self,
        locked: LockedOrder,
        lines: tuple[LineState, ...],
        *,
        reached_paid: bool,
        refunds: RefundFacts,
        actor_user_id: UUID,
    ) -> OrderStatus: ...


class OrderPayments(Protocol):
    async def reached_paid(self, order_id: UUID) -> bool:
        """`paid`, `partially_refunded` or `refunded`; read under the orders lock (BR-148)."""
        ...

    async def refund_facts(self, order_id: UUID) -> RefundFacts:
        """Read under the orders lock, like `reached_paid` (ADR-042)."""
        ...

    async def record_cash(
        self, *, order_id: UUID, amount_cents: int, currency: str, admin_id: UUID, at: datetime
    ) -> UUID:
        """The order's one cash payment; raises CashAlreadyRecordedError on a second."""
        ...

    async def rows(self, order_id: UUID) -> list[OrderPaymentRow]: ...

    async def cancellation_refund(
        self,
        locked: LockedOrder,
        cancelling: frozenset[UUID],
        *,
        actor_user_id: UUID,
        by_customer: bool,
        at: datetime,
        request_id: str | None,
        ip_hash: str | None,
    ) -> CancellationRefund | None:
        """The whole remaining balance of every line being cancelled (ADR-043)."""
        ...


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

    async def order_cancelled(
        self,
        locked: LockedOrder,
        cancelled: tuple[OrderLine, ...],
        *,
        order_cancelled: bool,
        amount_due_cents: int | None,
        refund_cents: int | None,
    ) -> None:
        """The `order_cancelled` email and `order.cancelled` notification (VS-031 Q3)."""
        ...

    async def cash_handed_over(
        self, locked: LockedOrder, *, payment_id: UUID, amount_cents: int, recorded_at: datetime
    ) -> None:
        """The delivered / picked-up email with the cash receipt, and its notification."""
        ...
