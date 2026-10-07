"""Authentication dependencies.

Identity owns authentication, so other bounded contexts depend on these rather
than decoding cookies themselves - one place decides what "authenticated"
means, and one place decides the error contract for failing it."""

from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Depends, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import ACCESS_COOKIE
from app.api.dependencies import get_session
from app.core.exceptions import ApiError
from app.core.security import verify_csrf_token
from app.identity.application.token_claims import AccessTokenClaims, decode_access_token
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import InvalidSessionError
from app.identity.infrastructure.repositories import UserRepository

logger = structlog.get_logger()

CSRF_HEADER = "X-CSRF-Token"


def unauthenticated_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="AUTH_REQUIRED",
        title="Authentication required",
        detail="A valid session is required for this request.",
    )


async def current_claims(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AccessTokenClaims:
    """Read the access-token cookie, verify it, or 401.

    Two checks, in this order. The signature and standard claims first, so a
    forged or expired token is refused with no database traffic at all and an
    unauthenticated caller cannot use this path to generate load. Then one
    indexed scalar read of `users.auth_epoch`: the token records the epoch it
    was minted under, and this refuses it once the account has moved past that.

    This is the part of ADR-006 that ADR-018 supersedes. ADR-006 traded
    revocation latency for a database-free authenticated path, and the trade was
    reasonable until VS-004 made immediate revocation a security requirement:
    without this read a password reset left every access token it had just
    revoked working for the remainder of its fifteen minutes.

    The epoch is read from PostgreSQL rather than a cache. It is the authority
    for an authentication decision, and a cache that answers *successfully* with
    a lost key - a restarted Redis, an evicted entry, a restored snapshot -
    would silently re-validate revoked credentials. That failure looks like
    normal operation, which is exactly what makes it unacceptable.
    """
    raw = request.cookies.get(ACCESS_COOKIE)
    if not raw:
        raise unauthenticated_error()
    try:
        claims = decode_access_token(raw)
    except InvalidSessionError as exc:
        raise unauthenticated_error() from exc

    current_epoch = await UserRepository(session).get_auth_epoch(claims.user_id)
    if current_epoch is None:
        # The account was hard-deleted (only ever the unverified-purge job) while
        # a token was still live.
        raise unauthenticated_error()
    if claims.auth_epoch != current_epoch:
        # Not `<`: an epoch ahead of the account's own is as impossible as one
        # behind it, and equality is the only relation that cannot be satisfied
        # by a stale credential.
        raise unauthenticated_error()
    return claims


async def current_user(
    claims: AccessTokenClaims = Depends(current_claims),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Load the authenticated user's own row, or 401.

    Use this only where the row is needed anyway; routes that need nothing
    beyond the token should keep depending on `current_claims` directly.

    Note this costs a *second* query on the same row: since ADR-018,
    `current_claims` already reads `users.auth_epoch`. That is one extra
    primary-key lookup on the only route that uses this dependency
    (`GET /api/v1/me`), and collapsing the two is recorded as a performance
    follow-up rather than fixed here - the obvious fix, having `current_claims`
    hydrate the whole row, would make every authenticated request pay for a full
    read (password hash included) to spare one route a scalar one.

    Because the read happens regardless here, it also re-checks
    `can_authenticate` rather than trusting the token for its full 15 minutes:
    an account disabled, anonymised or deleted a moment ago must not keep being
    served its own personal data until the next refresh."""
    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None or not user.can_authenticate:
        raise unauthenticated_error()
    return user


async def current_verified_user(user: User = Depends(current_user)) -> User:
    """The authenticated user, refused unless their email is verified.

    api-endpoints.md 3 defines "Verified Customer" as "Authenticated + verified
    email", and this is the first dependency to enforce it - every write path
    built so far has lived inside Identity, where verification was checked by
    the use case itself.

    Built on `current_user`, which re-reads the row, rather than on the token's
    `ver` claim. The claim is minted at login and lives for the access token's
    fifteen minutes, so a customer who verifies their email would otherwise keep
    being refused their own writes for up to a quarter of an hour after the
    state actually changed. One extra primary-key read on a write path is a
    trivial price for the dependency being *correct* rather than eventually
    correct.

    Deliberately no role check. "Verified Customer" is an authentication level
    in that table, not a role that excludes administrators, and adding a denial
    rule here would invent behaviour no document describes.
    """
    if not user.is_verified:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="EMAIL_VERIFICATION_REQUIRED",
            title="Email verification required",
            detail="Verify your email address before making this change.",
        )
    return user


async def require_csrf(
    request: Request, claims: AccessTokenClaims = Depends(current_claims)
) -> AccessTokenClaims:
    """Double-submit check for unsafe cookie-authenticated methods (SEC-03)."""
    if not verify_csrf_token(
        session_id=claims.session_id, presented=request.headers.get(CSRF_HEADER)
    ):
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CSRF_INVALID",
            title="CSRF token missing or invalid",
            detail=f"Send this session's CSRF cookie value in the {CSRF_HEADER} header.",
        )
    return claims


def user_agent(request: Request) -> str | None:
    # Truncated because it is attacker-controlled free text going into a TEXT
    # column; 512 is far more than any real browser sends.
    value = request.headers.get("User-Agent")
    return value[:512] if value else None


def not_found_error() -> ApiError:
    """The 404 an authenticated non-administrator gets from an admin route.

    SEC-10 requires 404 rather than 403: a 403 confirms the route exists, which
    tells an ordinary customer exactly which admin surface to go looking for.

    `title` and `detail` deliberately reproduce, byte for byte, what Starlette's
    own 404 handler emits for a path that matches no route at all (see
    `_STATUS_CODE_NAMES` in api/errors.py). Matching only the status and the
    code is not enough - a difference in the wording is just as good an oracle,
    and test_a_customer_cannot_distinguish_a_real_admin_route_from_a_missing_one
    is what holds these two in agreement."""
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="NOT_FOUND",
        title="Request cannot be completed",
        detail="Not Found",
    )


async def require_admin(claims: AccessTokenClaims = Depends(current_claims)) -> AccessTokenClaims:
    """The admin boundary: authenticated, administrator, MFA complete.

    The three failures are deliberately different, in this order:

    - no session at all      -> 401 AUTH_REQUIRED (from current_claims)
    - authenticated customer -> 404 NOT_FOUND     (SEC-10 information hiding)
    - admin without MFA      -> 401 MFA_REQUIRED  (SEC-04, api-endpoints.md:105)

    No challenge is opened here. Under the login-gated flow the only way to get
    a challenge is `POST /auth/login` (api-endpoints.md:252), so an
    administrator who reaches this branch is in one of two states, and neither
    is fixed by a step-up:

    - they have not finished enrolling, and need `/auth/mfa/setup` +
      `/setup/confirm`, which this very session is already entitled to call;
    - they hold a session predating the moment MFA was enabled on the account,
      and need to log in again to be challenged.

    Minting a challenge here would be a second, session-bound way to reach an
    MFA-complete session - exactly the parallel authentication path the slice
    is meant not to have.

    MFA state is read from the signed token rather than from Redis, keeping
    ADR-006's "no database round-trip on an ordinary authenticated request"
    property. A session created through `/auth/mfa/verify` is born with the
    claim set, and refresh carries it across rotation, so the claim cannot lag
    the session's real state."""
    if claims.role is not UserRole.ADMIN:
        raise not_found_error()

    if not claims.mfa_completed:
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="MFA_REQUIRED",
            title="Second factor required",
            detail="This session has not completed MFA. Sign in again to be challenged.",
        )

    return claims


class AdminBoundaryRoute(APIRoute):
    """Route class for every route under `/api/v1/admin`: the boundary runs
    before FastAPI touches the request body.

    FastAPI reads and parses a JSON body *before* it solves any dependency, so
    with `require_admin` only as a dependency a malformed body on a real admin
    write answered `400 MALFORMED_REQUEST` to anonymous callers and customers,
    where an imaginary path answers 401/404 - a route-existence oracle (SEC-10),
    and attacker-sized bodies were read before authentication. This wrapper
    runs the same two checks, `current_claims` then `require_admin`, on a
    short-lived read-only session first; the router-level dependency still runs
    afterwards and supplies the claims the handlers use. The cost is one extra
    `users.auth_epoch` read per admin request.
    """

    async def before_body(self, request: Request) -> None:
        """Runs after the boundary and before the body is read; a hook for subclasses."""
        return None

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            async with request.app.state.db_session_factory() as session:
                claims = await current_claims(request, session)
            await require_admin(claims)
            await self.before_body(request)
            return await handler(request)

        return guarded
