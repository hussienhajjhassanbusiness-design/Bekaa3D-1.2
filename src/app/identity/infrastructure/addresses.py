from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.address import Address, AddressDetails
from app.identity.domain.enums import Governorate
from app.identity.infrastructure.models import AddressModel, UserModel

_A = AddressModel
_COLUMNS = (
    _A.id,
    _A.user_id,
    _A.label,
    _A.recipient_name,
    _A.phone,
    _A.governorate,
    _A.city,
    _A.area,
    _A.street,
    _A.landmark_notes,
    _A.is_default,
    _A.deleted_at,
    _A.created_at,
    _A.updated_at,
)
_LIVE = _A.deleted_at.is_(None)


def _to_domain(row: Any) -> Address:
    return Address(
        id=row.id,
        user_id=row.user_id,
        details=AddressDetails(
            label=row.label,
            recipient_name=row.recipient_name,
            phone=row.phone,
            governorate=Governorate(row.governorate),
            city=row.city,
            area=row.area,
            street=row.street,
            landmark_notes=row.landmark_notes,
        ),
        is_default=row.is_default,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _values(details: AddressDetails) -> dict[str, Any]:
    return {
        "label": details.label,
        "recipient_name": details.recipient_name,
        "phone": details.phone,
        "governorate": details.governorate.value,
        "city": details.city,
        "area": details.area,
        "street": details.street,
        "landmark_notes": details.landmark_notes,
    }


class SqlAddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_address_book(self, user_id: UUID) -> None:
        """NO KEY UPDATE on the owner's row: serialises this user's address writes, while
        the KEY SHARE an address INSERT's foreign key takes stays compatible."""
        stmt = select(UserModel.id).where(UserModel.id == user_id).with_for_update(key_share=True)
        await self._session.execute(stmt)

    async def list_live(self, user_id: UUID) -> list[Address]:
        """Default first, then newest; bounded by the cap, so not paginated."""
        stmt = (
            select(*_COLUMNS)
            .where(_A.user_id == user_id, _LIVE)
            .order_by(_A.is_default.desc(), _A.created_at.desc(), _A.id.desc())
        )
        return [_to_domain(row) for row in (await self._session.execute(stmt)).all()]

    async def get_live(self, *, address_id: UUID, user_id: UUID) -> Address | None:
        stmt = select(*_COLUMNS).where(_A.id == address_id, _A.user_id == user_id, _LIVE)
        row = (await self._session.execute(stmt)).first()
        return _to_domain(row) if row is not None else None

    async def count_live(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(_A).where(_A.user_id == user_id, _LIVE)
        return (await self._session.execute(stmt)).scalar_one()

    async def clear_default(self, user_id: UUID) -> None:
        stmt = (
            update(_A)
            .where(_A.user_id == user_id, _A.is_default, _LIVE)
            .values(is_default=False, updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)

    async def add(self, *, user_id: UUID, details: AddressDetails, is_default: bool) -> Address:
        stmt = (
            postgresql.insert(_A)
            .values(user_id=user_id, is_default=is_default, **_values(details))
            .returning(*_COLUMNS)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def update(
        self, address_id: UUID, *, details: AddressDetails, is_default: bool
    ) -> Address:
        stmt = (
            update(_A)
            .where(_A.id == address_id)
            .values(is_default=is_default, updated_at=func.now(), **_values(details))
            .returning(*_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def soft_delete(self, address_id: UUID) -> None:
        stmt = (
            update(_A)
            .where(_A.id == address_id)
            .values(is_default=False, deleted_at=func.now(), updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)
