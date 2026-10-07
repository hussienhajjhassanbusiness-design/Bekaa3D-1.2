"""Admin user management (VS-009, F-116).

Mounted inside `/api/v1/admin`, whose router-level `require_admin` already
enforces authenticated + administrator + MFA-complete (VS-005), so nothing here
re-implements authorization. Every route still declares `require_admin` as a
parameter, because each one needs the acting administrator's id for the audit
trail - reads included, since they disclose PII (BUG-39). FastAPI caches the
dependency, so it resolves once per request either way.

Three endpoints, and deliberately not the fourth the endpoint catalogue lists
next to them: `POST /api/v1/admin/users/{user_id}/entitlements` belongs to
VS-017 and depends on tables that do not exist yet.
"""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.security import hash_ip
from app.identity.api.dependencies import (
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.identity.api.schemas import AdminUserDetail, AdminUserPage, AdminUserUpdate
from app.identity.application.commands.set_user_active import SetUserActive
from app.identity.application.token_claims import AccessTokenClaims
from app.identity.domain.exceptions import AccountNotMutableError, LastActiveAdministratorError
from app.identity.infrastructure.repositories import SessionRepository, UserRepository
from app.platform.public import SqlAuditWriter

router = APIRouter(prefix="/users", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

# `created_at` is an ISO-8601 timestamp and `id` is a UUID. A UUID contains no
# `|`, and neither does an ISO timestamp, so splitting on it is unambiguous -
# which `:` would not be, since an ISO timestamp carries colons in both the time
# and the UTC offset.
_CURSOR_SEPARATOR = "|"

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown user id, or caller is not an administrator."},
}


# --------------------------------------------------------------------------
# Cursor
#
# Local to Identity. VS-007 kept its settings cursor local, VS-008 its
# notifications cursor, VS-010 its catalogue cursor; this is the fourth, and
# extracting a shared helper stays a separate follow-up rather than something
# done inside a slice that has to be independently reviewable.
#
# Shaped after VS-008's, which is the right model here: ordering is by
# `(created_at, id)`, so the cursor has to carry both. `created_at` is not
# unique, and a cursor without the tie-breaker cannot address a row
# unambiguously.
# --------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, user_id: UUID) -> str:
    """Opaque, URL-safe, unpadded.

    Opaque because api-endpoints.md 2.2 says "the client does not construct or
    interpret cursors" - base64 is not secrecy, it is a signal that the value is
    ours and its format may change. Padding is stripped so the cursor survives a
    query string without escaping.
    """
    raw = f"{created_at.isoformat()}{_CURSOR_SEPARATOR}{user_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    """Decode a cursor into its `(created_at, id)` pair, or raise `ValueError`.

    Every field is parsed strictly rather than trusted. A cursor is a client-
    supplied value, and one that decoded into a half-valid pair would not fail
    loudly - it would silently page from the wrong place.
    """
    if raw is None:
        return None
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc

    created_raw, separator, id_raw = decoded.partition(_CURSOR_SEPARATOR)
    if not separator:
        raise ValueError("cursor is not a valid pagination cursor")
    try:
        created_at = datetime.fromisoformat(created_raw)
        user_id = UUID(id_raw)
    except ValueError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if created_at.tzinfo is None:
        # The column is timestamptz. A naive datetime would compare against it
        # under the server's timezone assumption rather than the one the cursor
        # was minted with, which silently shifts the page boundary.
        raise ValueError("cursor is not a valid pagination cursor")
    try:
        # asyncpg converts to UTC before sending; a time near year 1 or 9999
        # with a large offset has no UTC equivalent and overflowed there as a
        # 500 (BUG-36). Refused here as the malformed cursor it is.
        created_at.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    return created_at, user_id


def _decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    """Decode at the point of use, and report a bad cursor the usual way.

    Explicitly *not* attached to the query parameter as a Pydantic
    `AfterValidator`. VS-007 did exactly that and FastAPI did not apply it: the
    tampered cursor was accepted verbatim, used as a raw comparison key, and
    pagination never terminated. Decoding here removes the dependency on that
    behaviour entirely.

    `RequestValidationError` rather than a hand-built problem document, so a bad
    cursor produces what any other bad query parameter produces: the project's
    422 VALIDATION_ERROR, naming `cursor` in `errors`.
    """
    try:
        return _parse_cursor(raw)
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": str(exc), "type": "value_error"}]
        ) from exc


def _audit_context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


def _not_mutable_error(exc: AccountNotMutableError) -> ApiError:
    """409 INVALID_STATE_TRANSITION.

    Reusing the existing generic state-machine code rather than inventing one:
    "requested state-machine transition is illegal" (api-endpoints.md 182)
    describes activating an anonymised account exactly, and the error catalogue
    is a contract rather than a place to add synonyms.
    """
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Account is anonymised or deleted",
        detail=(
            f"User {exc.user_id} has been anonymised or deleted and can no longer be "
            "activated or deactivated."
        ),
    )


def _last_administrator_error(exc: LastActiveAdministratorError) -> ApiError:
    """409 INVALID_STATE_TRANSITION (BUG-38): same generic code as above."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Last active administrator",
        detail=(
            f"User {exc.user_id} is the last active administrator and cannot be "
            "deactivated; at least one must remain."
        ),
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get(
    "",
    response_model=AdminUserPage,
    summary="List and search accounts",
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "Invalid query parameter, including a tampered cursor."},
    },
)
async def list_users(
    request: Request,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    verified: bool | None = Query(default=None, description="Filter by email verification."),
    active: bool | None = Query(default=None, description="Filter by account activation."),
    search: str | None = Query(
        default=None,
        max_length=254,
        description="Case-insensitive partial match on email address.",
    ),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserPage:
    """Cursor-paginated, newest first. Sort is fixed; it is not a query
    parameter.

    One extra row is fetched beyond `limit` purely to answer "is there another
    page?" without a second COUNT query; it is dropped before serialising.

    The response carries email addresses, which is the point of an admin user
    list - so the read is audited (BUG-39, api-endpoints.md 533): who listed,
    which filters, and how many accounts came back. Never the search term or an
    address - a row holding the searched email would only move the leak from
    the server log into the database. `core/logging.py` keeps the `?search=`
    query string out of the access log.
    """
    rows = await UserRepository(session).list_page(
        limit=limit + 1,
        after=_decode_cursor(cursor),
        verified=verified,
        active=active,
        search=search,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="user.list_viewed",
        entity_type="user",
        entity_id=None,
        after_data={
            "filters": {"verified": verified, "active": active, "search": bool(search)},
            "result_count": len(page),
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return AdminUserPage(
        items=[AdminUserDetail.from_user(row) for row in page],
        next_cursor=_encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None,
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserDetail,
    summary="Read one account",
    responses=_ADMIN_RESPONSES,
)
async def read_user(
    user_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserDetail:
    """Audited as `user.viewed` against the account read (BUG-39). An unknown id
    is a 404 that discloses nothing, so it writes no row."""
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise not_found_error()
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="user.viewed",
        entity_type="user",
        entity_id=user.id,
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return AdminUserDetail.from_user(user)


@router.patch(
    "/{user_id}",
    response_model=AdminUserDetail,
    dependencies=[Depends(require_csrf)],
    summary="Activate or deactivate an account",
    responses={
        **_ADMIN_RESPONSES,
        403: {"description": "CSRF token missing or invalid."},
        409: {
            "description": (
                "`INVALID_STATE_TRANSITION` - the account is anonymised or deleted, or "
                "deactivating it would leave no active administrator."
            )
        },
        422: {"description": "Malformed body, or a field other than `is_active` was sent."},
    },
)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserDetail:
    """`is_active` is the only field this endpoint can change.

    An administrator may deactivate any account including their own, and may
    deactivate another administrator - with one exception (BUG-38): the last
    active administrator cannot be deactivated (409), because nobody could then
    reach the admin surface and recovery would need database access. Deactivating
    yourself while others remain ends your own session on the spot, which is a
    consequence of the revocation rather than a special case in it.
    """
    request_id, ip_hash = _audit_context(request)
    try:
        result = await SetUserActive(
            UserRepository(session), SessionRepository(session), SqlAuditWriter(session)
        ).execute(
            user_id=user_id,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except AccountNotMutableError as exc:
        raise _not_mutable_error(exc) from exc
    except LastActiveAdministratorError as exc:
        raise _last_administrator_error(exc) from exc
    if result is None:
        raise not_found_error()
    return AdminUserDetail.from_user(result.user)
