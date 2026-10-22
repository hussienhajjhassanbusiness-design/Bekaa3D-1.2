"""Checkout's share-locked read of the customer's address, through Identity's public surface."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.public import lock_checkout_address
from app.ordering.application.ports import CheckoutAddressSnapshot


class SqlCheckoutAddresses:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_for_share(
        self, address_id: UUID, user_id: UUID
    ) -> CheckoutAddressSnapshot | None:
        found = await lock_checkout_address(self._session, address_id=address_id, user_id=user_id)
        if found is None:
            return None
        return CheckoutAddressSnapshot(
            recipient_name=found.recipient_name,
            phone=found.phone,
            governorate=found.governorate,
            city=found.city,
            area=found.area,
            street=found.street,
            landmark_notes=found.landmark_notes,
        )
