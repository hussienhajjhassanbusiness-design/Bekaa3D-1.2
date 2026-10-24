"""Fulfillment's published surface (VS-031): the customer's own cancel, for Ordering's
`POST /me/orders/{id}/cancel`, which builds the `OrderDetail` itself (ADR-043 Q13)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.fulfillment.application.cancel_lines import CancelContext, CancelDeps, cancel_by_customer
from app.fulfillment.infrastructure.delivery_side import (
    SqlDeliveryNotices,
    SqlDeliveryOrders,
    SqlOrderPayments,
)
from app.ordering.public import OrderStatus
from app.platform.public import SqlAuditWriter

__all__ = ["cancel_order_by_customer"]


async def cancel_order_by_customer(
    session: AsyncSession,
    *,
    order_id: UUID,
    user_id: UUID,
    at: datetime,
    note: str | None,
    request_id: str | None,
    ip_hash: str | None,
) -> OrderStatus:
    """On the caller's session. Raises LineNotFoundError (404), OrderNotCancellableError
    (409), or OrderTotalMismatchError / RefundExceedsAvailableError (409, nothing written)."""
    deps = CancelDeps(
        SqlDeliveryOrders(session),
        SqlOrderPayments(session),
        SqlAuditWriter(session),
        SqlDeliveryNotices(session),
    )
    outcome = await cancel_by_customer(
        deps, order_id=order_id, ctx=CancelContext(user_id, at, note, request_id, ip_hash)
    )
    return outcome.order_status
