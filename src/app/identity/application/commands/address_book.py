"""Address book writes (VS-026, FR-03). Each takes the per-user address-book lock first, so
default switches, the first-address default and the cap count are serialised per user;
the partial unique index on `addresses` is the backstop."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.identity.application.ports import AddressStore
from app.identity.domain.address import (
    Address,
    AddressDetails,
    becomes_default,
    check_capacity,
)
from app.identity.domain.exceptions import AddressNotFoundError


class _AddressCommand:
    def __init__(self, addresses: AddressStore) -> None:
        self._addresses = addresses

    async def _locked_live(self, *, user_id: UUID, address_id: UUID) -> Address:
        await self._addresses.lock_address_book(user_id)
        address = await self._addresses.get_live(address_id=address_id, user_id=user_id)
        if address is None:
            raise AddressNotFoundError(address_id)
        return address


class CreateAddress(_AddressCommand):
    async def execute(
        self, *, user_id: UUID, details: AddressDetails, make_default: bool
    ) -> Address:
        await self._addresses.lock_address_book(user_id)
        live_count = await self._addresses.count_live(user_id)
        check_capacity(live_count)
        is_default = becomes_default(requested=make_default, live_count=live_count)
        if is_default:
            await self._addresses.clear_default(user_id)
        return await self._addresses.add(user_id=user_id, details=details, is_default=is_default)


class UpdateAddress(_AddressCommand):
    async def execute(
        self,
        *,
        user_id: UUID,
        address_id: UUID,
        changes: Mapping[str, Any],
        make_default: bool | None,
    ) -> Address:
        """`make_default` None leaves the flag alone; False clears it (VS-026 Q8)."""
        address = await self._locked_live(user_id=user_id, address_id=address_id)
        details = address.details.changed(**changes) if changes else address.details
        is_default = address.is_default if make_default is None else make_default
        if is_default and not address.is_default:
            await self._addresses.clear_default(user_id)
        return await self._addresses.update(
            address_id, user_id=user_id, details=details, is_default=is_default
        )


class SetDefaultAddress(_AddressCommand):
    async def execute(self, *, user_id: UUID, address_id: UUID) -> Address:
        address = await self._locked_live(user_id=user_id, address_id=address_id)
        if address.is_default:
            return address
        await self._addresses.clear_default(user_id)
        return await self._addresses.update(
            address_id, user_id=user_id, details=address.details, is_default=True
        )


class DeleteAddress(_AddressCommand):
    async def execute(self, *, user_id: UUID, address_id: UUID) -> None:
        """Soft delete; deleting the default leaves none, nothing is promoted (VS-026 Q5)."""
        await self._locked_live(user_id=user_id, address_id=address_id)
        await self._addresses.soft_delete(address_id, user_id=user_id)
