"""The read-only audit-log viewer (VS-012b, F-117, api-endpoints.md 26).

Mounted inside `/api/v1/admin`, whose router-level `require_admin` already
enforces authenticated + administrator + MFA-complete (VS-005), so nothing here
re-implements authorization.

Two `GET`s and nothing else. No create, update or delete route exists, so any
other method falls through to the admin boundary's catch-all and answers like a
real path with the wrong method. Reading the log is not itself audited.

Filters are the seven api-endpoints.md 31 names. Unknown query parameters are
ignored, as on every other list endpoint, although api-endpoints.md 31 asks for
a 400 - the project-wide follow-up is recorded in the vertical slice plan
(VS-012) rather than special-cased here.
"""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.identity.public import AdminBoundaryRoute, not_found_error
from app.platform.api.schemas import AuditLogPage, AuditLogRead
from app.platform.infrastructure.repositories import AuditLogRepository

admin_router = APIRouter(prefix="/audit-logs", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

# Same separator, and for the same reason, as the VS-009 user cursor: neither an
# ISO timestamp nor a UUID contains `|`.
_CURSOR_SEPARATOR = "|"

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown audit entry, or caller is not an administrator."},
}


# --------------------------------------------------------------------------
# Cursor
#
# Local to this router, like the settings (VS-007), notifications (VS-008),
# catalogue (VS-010) and admin-user (VS-009) cursors; this is the fifth, and
# extracting a shared helper stays a separate follow-up. Shaped exactly like the
# VS-009 one: the order is `(created_at, id)`, so the cursor carries both.
# --------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, audit_id: UUID) -> str:
    raw = f"{created_at.isoformat()}{_CURSOR_SEPARATOR}{audit_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
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
        audit_id = UUID(id_raw)
    except ValueError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if not _is_utc_representable(created_at):
        raise ValueError("cursor is not a valid pagination cursor")
    return created_at, audit_id


def _is_utc_representable(moment: datetime) -> bool:
    """Aware, and with a UTC equivalent.

    A naive value would be compared under the server's timezone rather than the
    caller's. And asyncpg converts to UTC before sending, so a time near year 1
    or 9999 with a large offset overflowed there as a 500 (BUG-36)."""
    if moment.tzinfo is None:
        return False
    try:
        moment.astimezone(UTC)
    except OverflowError:
        return False
    return True


def _invalid(field: str, message: str) -> RequestValidationError:
    """The project's ordinary 422 VALIDATION_ERROR, naming the query parameter.

    Raised at the point of use rather than through a Pydantic validator on the
    parameter: VS-007 found FastAPI did not apply one to a query parameter."""
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


def _decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    try:
        return _parse_cursor(raw)
    except ValueError as exc:
        raise _invalid("cursor", str(exc)) from exc


def _check_range(created_after: datetime | None, created_before: datetime | None) -> None:
    for field, moment in (("created_after", created_after), ("created_before", created_before)):
        if moment is not None and not _is_utc_representable(moment):
            raise _invalid(field, "must be a timestamp with a UTC offset, e.g. 2026-10-01T00:00Z")
    if created_after is not None and created_before is not None and created_before <= created_after:
        # The range is half-open, so an equal pair is empty by definition, and
        # an inverted one is a mistake the caller should hear about.
        raise _invalid("created_before", "must be later than created_after")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@admin_router.get(
    "",
    response_model=AuditLogPage,
    summary="Search the audit log",
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "Invalid query parameter, a tampered cursor or an empty range."},
    },
)
async def list_audit_logs(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    actor_user_id: UUID | None = Query(default=None, description="Who acted."),
    action: str | None = Query(default=None, max_length=200, description="Exact action name."),
    entity_type: str | None = Query(default=None, max_length=200),
    entity_id: UUID | None = Query(default=None),
    request_id: str | None = Query(default=None, max_length=128),
    created_after: datetime | None = Query(
        default=None, description="Inclusive lower bound; must carry a UTC offset."
    ),
    created_before: datetime | None = Query(
        default=None, description="Exclusive upper bound; must carry a UTC offset."
    ),
    session: AsyncSession = Depends(get_session),
) -> AuditLogPage:
    """Cursor-paginated, newest first (`-created_at`, then `-id`). Sort is fixed.

    Filters combine with AND. One extra row is fetched beyond `limit` to answer
    "is there another page?" without a COUNT.
    """
    after = _decode_cursor(cursor)
    _check_range(created_after, created_before)
    rows = await AuditLogRepository(session).list_page(
        limit=limit + 1,
        after=after,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        created_after=created_after,
        created_before=created_before,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return AuditLogPage(
        items=[AuditLogRead.from_entry(row) for row in page],
        next_cursor=_encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None,
    )


@admin_router.get(
    "/{audit_id}",
    response_model=AuditLogRead,
    summary="Read one audit entry",
    responses=_ADMIN_RESPONSES,
)
async def read_audit_log(
    audit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> AuditLogRead:
    entry = await AuditLogRepository(session).get_by_id(audit_id)
    if entry is None:
        raise not_found_error()
    return AuditLogRead.from_entry(entry)
