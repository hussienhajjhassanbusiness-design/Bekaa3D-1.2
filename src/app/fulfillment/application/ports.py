"""What the delivery use case needs from Ordering and from the notices adapter."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.ordering.public import LockedOrder, OrderLine, OrderStatus


class DeliveryOrders(Protocol):
    async def lock(self, order_id: UUID) -> LockedOrder | None:
        """`orders` FOR UPDATE, then its lines by id (ADR-024 d9)."""
        ...

    async def mark_delivered(
        self, locked: LockedOrder, *, line_id: UUID, admin_id: UUID, at: datetime
    ) -> tuple[OrderLine, OrderStatus]: ...


class DeliveryNotices(Protocol):
    async def stl_delivered(self, locked: LockedOrder, line: OrderLine) -> None:
        """The customer's outbox email and in-app notification, on the caller's session."""
        ...
