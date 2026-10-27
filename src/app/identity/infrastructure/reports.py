"""Identity's reporting read (VS-043): customer counts, never an email. Unlocked, read-only."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel

_U = UserModel
_REGISTERED = (
    _U.role == UserRole.CUSTOMER,
    _U.email_verified_at.is_not(None),
    _U.anonymized_at.is_(None),
    _U.deleted_at.is_(None),
)


@dataclass(frozen=True)
class CustomerCountsRow:
    registered: int
    new_in_range: int


async def customer_counts(
    session: AsyncSession, *, created_from: datetime, created_to: datetime
) -> CustomerCountsRow:
    """Registered customers now, and those of them created in [created_from, created_to)."""
    in_range = (_U.created_at >= created_from) & (_U.created_at < created_to)
    query = select(func.count(), func.count().filter(in_range)).where(*_REGISTERED)
    registered, new = (await session.execute(query)).tuples().one()
    return CustomerCountsRow(int(registered), int(new))
