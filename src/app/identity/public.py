"""Identity's published surface for other bounded contexts.

Another context may import from here or from `app.identity.application.ports`,
and from nowhere else in Identity (enforced by
`tests/unit/test_deep_architecture.py`): the admin boundary and the current-user
dependencies its routers mount, the `User` entity those dependencies return, and
the token claims, read through the token-claims port.
"""

from app.identity.api.dependencies import (
    AdminBoundaryRoute,
    current_user,
    current_verified_user,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.identity.application.token_claims import AccessTokenClaims
from app.identity.domain.entities import User

__all__ = [
    "AccessTokenClaims",
    "AdminBoundaryRoute",
    "User",
    "current_user",
    "current_verified_user",
    "not_found_error",
    "require_admin",
    "require_csrf",
]
