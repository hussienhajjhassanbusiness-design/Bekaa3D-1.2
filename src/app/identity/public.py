"""Identity's published surface for other bounded contexts.

Another context may import from here or from `app.identity.application.ports`,
and from nowhere else in Identity (enforced by
`tests/unit/test_deep_architecture.py`): the admin boundary and the current-user
dependencies its routers mount, the `User` entity those dependencies return, and
the token claims, read through the token-claims port.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.api.dependencies import (
    AdminBoundaryRoute,
    current_user,
    current_verified_user,
    not_found_error,
    require_admin,
    require_csrf,
    verified_user_short_read,
)
from app.identity.application.token_claims import AccessTokenClaims
from app.identity.domain.entities import User
from app.identity.infrastructure.repositories import UserRepository

__all__ = [
    "AccessTokenClaims",
    "AdminBoundaryRoute",
    "User",
    "active_administrator_ids",
    "current_user",
    "current_verified_user",
    "not_found_error",
    "require_admin",
    "require_csrf",
    "verified_user_short_read",
]


async def active_administrator_ids(session: AsyncSession) -> list[UUID]:
    """Active, live administrators, read in the caller's transaction (VS-034 notifications)."""
    return await UserRepository(session).active_administrator_ids()
