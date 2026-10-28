"""Identity's published surface for other bounded contexts.

Another context may import from here or from `app.identity.application.ports`,
and from nowhere else in Identity (enforced by
`tests/unit/test_deep_architecture.py`): the admin boundary and the current-user
dependencies its routers mount, the `User` entity those dependencies return, and
the token claims, read through the token-claims port.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.api.dependencies import (
    AdminBoundaryRoute,
    current_user,
    current_verified_user,
    not_found_error,
    require_admin,
    require_csrf,
    unauthenticated_error,
    verified_user_short_read,
)
from app.identity.application.token_claims import AccessTokenClaims
from app.identity.domain.address import Address
from app.identity.domain.entities import User
from app.identity.infrastructure.addresses import SqlAddressRepository
from app.identity.infrastructure.reports import CustomerCountsRow, customer_counts
from app.identity.infrastructure.repositories import UserRepository

__all__ = [
    "AccessTokenClaims",
    "Address",
    "AdminBoundaryRoute",
    "CheckoutAddress",
    "CustomerCountsRow",
    "User",
    "account_is_live",
    "active_administrator_contacts",
    "active_administrator_ids",
    "addresses_for_export",
    "current_user",
    "current_verified_user",
    "customer_counts",
    "lock_checkout_address",
    "not_found_error",
    "require_admin",
    "require_csrf",
    "unauthenticated_error",
    "user_emails",
    "verified_user_short_read",
]


async def account_is_live(session: AsyncSession, user_id: UUID) -> bool:
    """False once deactivated or anonymised; checkout reads it after its lock (ADR-047)."""
    return await UserRepository(session).can_authenticate(user_id)


async def active_administrator_ids(session: AsyncSession) -> list[UUID]:
    """Active, live administrators, read in the caller's transaction (VS-034 notifications)."""
    return await UserRepository(session).active_administrator_ids()


async def active_administrator_contacts(session: AsyncSession) -> list[tuple[UUID, str]]:
    """Active, verified administrators and their emails (VS-024 payment alerts). The
    emails go to the outbox only; never log them."""
    return await UserRepository(session).active_administrator_contacts()


async def user_emails(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, str]:
    """Account emails by id, read in the caller's transaction (VS-039 admin offer queue)."""
    return await UserRepository(session).emails_by_id(user_ids)


async def addresses_for_export(session: AsyncSession, user_id: UUID) -> list[Address]:
    """VS-044: every address of the user, deleted ones included (`deleted_at` set)."""
    return await SqlAddressRepository(session).list_all_for_user(user_id)


@dataclass(frozen=True)
class CheckoutAddress:
    """The fields an order snapshots from an address (VS-028 plan 3.3)."""

    recipient_name: str
    phone: str
    governorate: str
    city: str
    area: str | None
    street: str | None
    landmark_notes: str


async def lock_checkout_address(
    session: AsyncSession, *, address_id: UUID, user_id: UUID
) -> CheckoutAddress | None:
    """`FOR SHARE` read of a live address; None for unknown, foreign and deleted alike."""
    address = await SqlAddressRepository(session).get_live_for_share(
        address_id=address_id, user_id=user_id
    )
    if address is None:
        return None
    d = address.details
    return CheckoutAddress(
        recipient_name=d.recipient_name,
        phone=d.phone,
        governorate=d.governorate.value,
        city=d.city,
        area=d.area,
        street=d.street,
        landmark_notes=d.landmark_notes,
    )
