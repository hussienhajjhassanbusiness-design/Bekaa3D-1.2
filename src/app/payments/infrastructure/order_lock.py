"""The guard every refund and chargeback fact read runs first (ADR-042 d9): the rows can
change only under the order's row lock, so a reader without that lock is refused."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.domain.exceptions import OrderLockRequiredError

# xmax is this transaction after `FOR UPDATE`; xmin is, once this transaction updated it.
_HOLDS_ORDER_LOCK = text(
    "SELECT (xmax::text = pg_current_xact_id()::xid::text"
    " OR xmin::text = pg_current_xact_id()::xid::text) FROM orders WHERE id = :o"
)


async def require_order_lock(session: AsyncSession, order_id: UUID) -> None:
    """Refuse a refund-fact read made without `lock_order_for_change` in this transaction."""
    held = (await session.execute(_HOLDS_ORDER_LOCK, {"o": order_id})).scalar()
    if not held:
        raise OrderLockRequiredError(f"order {order_id} is not locked by this transaction")
