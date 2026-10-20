"""Negotiation's ports over other contexts' public surfaces, all in the caller's session."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.public import NotificationType, create_notification
from app.identity.public import active_administrator_ids, user_emails
from app.ordering.public import stl_owned


class OrderingStlOwnership:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owns(self, user_id: UUID, product_id: UUID) -> bool:
        return await stl_owned(self._session, user_id=user_id, product_id=product_id)


class EngagementOfferNotifier:
    """One `offer` notification per recipient, atomic with the offer change (no savepoint)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def notify_administrators(self, payload: dict[str, Any]) -> None:
        for admin_id in await active_administrator_ids(self._session):
            await self.notify_customer(admin_id, payload)

    async def notify_customer(self, user_id: UUID, payload: dict[str, Any]) -> None:
        await create_notification(
            self._session,
            user_id=user_id,
            notification_type=NotificationType.OFFER,
            payload=payload,
        )


class IdentityCustomerDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def emails(self, user_ids: list[UUID]) -> dict[UUID, str]:
        return await user_emails(self._session, user_ids)
