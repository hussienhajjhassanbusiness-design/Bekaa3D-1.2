"""Identity's `AccountErasure` adapter (VS-045): each context's share, through its `public`."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import anonymise_contact_messages, erase_wishlist_items
from app.identity.application.ports import ErasureCounts
from app.negotiation.public import lock_live_offers_for_erasure, withdraw_offers_for_erasure
from app.ordering.public import (
    erase_orders,
    lock_cart_for_erasure,
    lock_orders_for_erasure,
    open_order_exists,
)
from app.payments.public import unsettled_refund_exists
from app.platform.public import anonymise_outbox


class SqlAccountErasure:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_orders(self, user_id: UUID) -> None:
        await lock_orders_for_erasure(self._session, user_id)

    async def lock_cart(self, user_id: UUID) -> None:
        await lock_cart_for_erasure(self._session, user_id)

    async def lock_live_offers(self, user_id: UUID) -> None:
        await lock_live_offers_for_erasure(self._session, user_id)

    async def open_order_exists(self, user_id: UUID) -> bool:
        return await open_order_exists(self._session, user_id)

    async def unsettled_refund_exists(self, user_id: UUID) -> bool:
        return await unsettled_refund_exists(self._session, user_id)

    async def erase(self, user_id: UUID, *, email: str, at: datetime) -> ErasureCounts:
        s = self._session
        return ErasureCounts(
            orders=await erase_orders(s, user_id, email=email, at=at),
            offers_withdrawn=await withdraw_offers_for_erasure(s, user_id, at=at),
            wishlist_items=await erase_wishlist_items(s, user_id),
            contact_messages=await anonymise_contact_messages(s, user_id, email=email),
            outbox_rows=await anonymise_outbox(s, user_id, email=email, at=at),
        )
