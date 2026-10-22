"""A stand-in for VS-031's block-inserting cancel, with the lock order VS-031 must use
(ADR-024 d9): the order and its lines, then the customer's cart, then the cash phone lock.
No refund step: there is no `refunds` table yet (VS-028 plan 6.3 R3)."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.ordering.infrastructure.carts import SqlCartStore
from app.ordering.public import (
    CancelReason,
    cash_block_store,
    lock_cash_phone,
    lock_order_for_change,
)

LOCK_TIMEOUT = "5s"


async def cancel_with_block(
    engine: AsyncEngine,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    phone_hash: str,
    holding: asyncio.Event | None = None,
    release: asyncio.Event | None = None,
) -> None:
    """Cancel a cash order as refused and block its customer and phone, in one transaction.
    With `holding`, it signals once the phone lock is held and waits for `release`."""
    async with async_sessionmaker(engine)() as session, session.begin():
        await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        locked = await lock_order_for_change(session, order_id)
        assert locked is not None
        await SqlCartStore(session).lock(user_id, create=True)
        await lock_cash_phone(session, phone_hash)
        if holding is not None and release is not None:
            holding.set()
            await asyncio.wait_for(release.wait(), timeout=10)
        now = datetime.now(UTC)
        await cash_block_store(session).insert_block(
            user_id=user_id,
            phone_hash=phone_hash,
            order_id=order_id,
            reason=CancelReason.REFUSED,
            at=now,
        )
        await session.execute(
            text(
                "UPDATE order_items SET fulfillment_status = 'cancelled', cancelled_at = :t,"
                " cancel_reason = 'refused' WHERE order_id = :o"
            ),
            {"t": now, "o": order_id},
        )
        await session.execute(
            text("UPDATE orders SET status = 'cancelled', cancelled_at = :t WHERE id = :o"),
            {"t": now, "o": order_id},
        )
