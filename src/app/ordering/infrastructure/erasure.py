"""Ordering's share of an account deletion (VS-045, ADR-047). The orders lock comes first, the
cart's second (ADR-041, ADR-024 d9); the rest runs under both."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.domain.enums import OrderStatus
from app.ordering.domain.order_status import TERMINAL_LINE_STATES
from app.ordering.infrastructure.carts import SqlCartStore
from app.ordering.infrastructure.models import OrderItemModel, OrderModel

_O, _I = OrderModel, OrderItemModel
_OPEN_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.IN_PROGRESS)


async def lock_orders_for_erasure(session: AsyncSession, user_id: UUID) -> None:
    stmt = select(_O.id).where(_O.user_id == user_id).order_by(_O.id).with_for_update()
    await session.execute(stmt)


async def lock_cart_for_erasure(session: AsyncSession, user_id: UUID) -> None:
    """Created if missing, so a checkout already waiting on it then finds it empty."""
    await SqlCartStore(session).lock(user_id, create=True)


async def open_order_exists(session: AsyncSession, user_id: UUID) -> bool:
    """A live line counts too: `partially_refunded` can still have one in progress."""
    live_line = exists().where(
        _I.user_id == user_id, _I.fulfillment_status.not_in(TERMINAL_LINE_STATES)
    )
    open_order = exists().where(_O.user_id == user_id, _O.status.in_(_OPEN_STATUSES))
    return bool(await session.scalar(select(or_(open_order, live_line))))


async def erase_orders(session: AsyncSession, user_id: UUID, *, email: str, at: datetime) -> int:
    """Strips every order's personal fields (`ck_orders_anonymised_shape`) and empties the
    cart. `governorate` and `admin_note` stay (ADR-047). Returns the orders changed."""
    carts = SqlCartStore(session)
    cart = await carts.lock(user_id, create=True)
    await carts.clear(cart.id)
    stmt = (
        update(_O)
        .where(_O.user_id == user_id, _O.anonymized_at.is_(None))
        .values(
            customer_email_snapshot=email,
            recipient_name=None,
            contact_phone_snapshot=None,
            contact_phone_hash=None,
            city=None,
            area=None,
            street=None,
            landmark_notes=None,
            customer_note=None,
            anonymized_at=at,
            updated_at=at,
        )
        .returning(_O.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.execute(stmt)).all())
