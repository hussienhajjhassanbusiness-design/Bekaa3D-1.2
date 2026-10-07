"""Admin settings editor and the public allowlist endpoint.

Two routers, deliberately separate. The admin one is mounted inside
`/api/v1/admin`, whose router-level `require_admin` already enforces
authenticated + administrator + MFA-complete (VS-005), so nothing here
re-implements authorization. The public one is unauthenticated and returns a
fixed five-field schema.
"""

import base64
import binascii
import re
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import rate_limiter
from app.core.security import hash_ip
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.platform.api.schemas import PublicSettingsRead, SettingPage, SettingRead, SettingUpdate
from app.platform.application.commands.update_setting import UpdateSetting
from app.platform.domain.entities import Setting
from app.platform.domain.enums import SettingType
from app.platform.domain.exceptions import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingTypeMismatchError,
)
from app.platform.domain.settings_registry import (
    PUBLIC_KEYS,
    definition_for,
    validate_value,
)
from app.platform.infrastructure.repositories import AuditLogRepository, SettingRepository

admin_router = APIRouter(prefix="/settings", tags=["admin"], route_class=AdminBoundaryRoute)
public_router = APIRouter(prefix="/settings", tags=["settings"])

# The public endpoint is hit by every page load - the floating WhatsApp button
# is on every page - so it needs a far more generous allowance than the auth
# routes, which are 5-60/hour. 600/hour per IP is ten page loads a minute
# sustained, which no human browsing produces and a scraper does. A V1
# design-time figure, like the other limits in this codebase.
PUBLIC_RATE_LIMIT = 600
PUBLIC_RATE_WINDOW_SECONDS = 3600

_PUBLIC_LIMIT = rate_limiter(
    key_prefix="settings:public",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

# A cursor decodes to a setting key, and keys are lowercase identifiers. Shape
# checking it turns a tampered cursor into a clear validation error instead of a
# silently empty page.
_KEY_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")


def _encode_cursor(key: str) -> str:
    """Opaque, URL-safe, unpadded.

    Opaque because api-endpoints.md 2.2 says "the client does not construct or
    interpret cursors" - base64 is not secrecy, it is a signal that the value is
    ours and its format may change. Padding is stripped so the cursor survives a
    query string without escaping.
    """
    return base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii").rstrip("=")


def _validate_cursor(raw: str | None) -> str | None:
    """Decode a cursor, or raise so Pydantic reports it the standard way.

    Raising `ValueError` here means FastAPI's `RequestValidationError` handler
    produces the project's ordinary `422 VALIDATION_ERROR` problem document,
    with the offending parameter named in `errors`. That is the existing
    contract for a bad query parameter, so a tampered cursor needs no new error
    code of its own.
    """
    if raw is None:
        return None
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if not _KEY_SHAPE.match(decoded):
        raise ValueError("cursor is not a valid pagination cursor")
    return decoded


def _decode_cursor(raw: str | None) -> str | None:
    """Decode the cursor at the point of use, and report a bad one the usual way.

    An earlier version attached `_validate_cursor` to the parameter as a
    Pydantic `AfterValidator`. FastAPI did not apply it to the query parameter,
    so a tampered cursor was accepted verbatim and then used as a key
    comparison - which did not fail, it silently paged from the wrong place and
    never terminated. Decoding explicitly here removes the dependency on that
    behaviour entirely.

    `RequestValidationError` rather than a hand-built problem document, so a bad
    cursor produces exactly what any other bad query parameter produces: the
    project's 422 VALIDATION_ERROR, naming `cursor` in `errors`.
    """
    try:
        return _validate_cursor(raw)
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": str(exc), "type": "value_error"}]
        ) from exc


def _setting_invalid_error(exc: InvalidSettingValueError) -> ApiError:
    """422 SETTING_INVALID (api-endpoints.md 5.1).

    Distinct from the 422 VALIDATION_ERROR that a malformed *envelope* produces:
    that one means the request body was the wrong shape, this one means the body
    was fine but the value is not allowed for this key.
    """
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="SETTING_INVALID",
        title="Setting value is not valid",
        detail="; ".join(exc.reasons),
    )


@admin_router.get(
    "",
    response_model=SettingPage,
    summary="List typed settings",
    responses={
        401: {"description": "No session, or MFA not completed."},
        404: {"description": "Caller is not an administrator."},
        422: {"description": "Invalid query parameter, including a tampered cursor."},
    },
)
async def list_settings(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    prefix: str | None = Query(default=None, max_length=64, description="Key prefix filter."),
    type: SettingType | None = Query(default=None, description="Filter by declared type."),
    session: AsyncSession = Depends(get_session),
) -> SettingPage:
    """Cursor-paginated, ordered by key.

    One extra row is fetched beyond `limit` purely to answer "is there another
    page?" without a second `COUNT` query; it is dropped before serialising.
    """
    rows = await SettingRepository(session).list_page(
        limit=limit + 1, after_key=_decode_cursor(cursor), prefix=prefix, setting_type=type
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return SettingPage(
        items=[SettingRead.from_setting(setting) for setting in page],
        next_cursor=_encode_cursor(page[-1].key) if has_more and page else None,
    )


async def _load_registered(session: AsyncSession, key: str) -> Setting:
    """Fetch a setting that must be both registered and present.

    An unregistered key and a missing row both answer 404, and identically. The
    caller cannot tell "no such setting" from "not an administrator" either,
    since the admin boundary returns the same 404 - which is the SEC-10
    behaviour, and incidentally stops anyone enumerating setting names.
    """
    definition_for(key)
    setting = await SettingRepository(session).get_by_key(key)
    if setting is None:
        raise SettingNotFoundError(key)
    return setting


@admin_router.get(
    "/{key}",
    response_model=SettingRead,
    summary="Read one typed setting",
    responses={
        401: {"description": "No session, or MFA not completed."},
        404: {"description": "Unknown setting key, or caller is not an administrator."},
    },
)
async def read_setting(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> SettingRead:
    try:
        setting = await _load_registered(session, key)
    except SettingNotFoundError as exc:
        raise not_found_error() from exc
    return SettingRead.from_setting(setting)


@admin_router.patch(
    "/{key}",
    response_model=SettingRead,
    dependencies=[Depends(require_csrf)],
    summary="Change one typed setting",
    responses={
        401: {"description": "No session, or MFA not completed."},
        403: {"description": "CSRF token missing or invalid."},
        404: {"description": "Unknown setting key, or caller is not an administrator."},
        422: {"description": "Value fails its declared type or range (SETTING_INVALID)."},
    },
)
async def update_setting(
    key: str,
    body: SettingUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SettingRead:
    """Type/range validated, audited, and atomic with its audit row.

    CSRF is required even though the endpoint table does not spell it out: this
    is an unsafe cookie-authenticated method, and SEC-03 covers all of them.
    """
    use_case = UpdateSetting(
        settings_repo=SettingRepository(session),
        audit_repo=AuditLogRepository(session),
    )
    ip = client_ip(request)
    try:
        result = await use_case.execute(
            key=key,
            value=body.value,
            actor_user_id=claims.user_id,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except SettingNotFoundError as exc:
        raise not_found_error() from exc
    except InvalidSettingValueError as exc:
        raise _setting_invalid_error(exc) from exc

    return SettingRead.from_setting(result.setting)


@public_router.get(
    "/public",
    response_model=PublicSettingsRead,
    dependencies=[Depends(_PUBLIC_LIMIT)],
    summary="Read the publicly visible settings",
    responses={429: {"description": "Rate limit exceeded."}},
)
async def read_public_settings(
    session: AsyncSession = Depends(get_session),
) -> PublicSettingsRead:
    """The five allowlisted settings, read by key.

    Two separate guarantees stop an internal setting leaking here, and both have
    to be removed for one to escape: only the allowlisted keys are queried at
    all, and the response model has a field for each of those five and nothing
    else. Adding a row to the `settings` table therefore cannot make it public.

    A missing or invalid row raises rather than being defaulted. These are
    seeded by migration, so absence means a broken deployment - and silently
    reporting `accepting_orders: true` because the row could not be read would
    tell customers the shop is open when the server does not know that.
    """
    found = await SettingRepository(session).get_many(PUBLIC_KEYS)
    values: dict[str, Any] = {}
    for key in PUBLIC_KEYS:
        setting = found.get(key)
        if setting is None:
            raise SettingNotFoundError(key)
        definition = definition_for(key)
        if setting.type is not definition.type:
            raise SettingTypeMismatchError(key, setting.type, definition.type)
        values[key] = validate_value(key, setting.value)
    return PublicSettingsRead(**values)
