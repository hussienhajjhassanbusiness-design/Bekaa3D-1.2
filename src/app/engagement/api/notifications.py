"""The customer's own notification centre, mounted under `/api/v1/me`.

Two endpoints with deliberately different authentication levels, both taken
from api-endpoints.md 14.3: reading is `Authenticated`, because a customer who
has not yet verified their email can still be shown their account notifications;
marking read is `Verified Customer`, because it is a write.
"""

import base64
import binascii
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.engagement.api.schemas import NotificationPage, NotificationRead, NotificationUpdate
from app.engagement.infrastructure.repositories import NotificationRepository
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)

router = APIRouter(prefix="/me/notifications", tags=["notifications"])

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

# `created_at` is an ISO-8601 timestamp and `id` is a UUID; neither can contain
# this character, so splitting is unambiguous.
_CURSOR_SEPARATOR = "|"


# --------------------------------------------------------------------------
# Cursor
#
# Local to Engagement, and not shared with VS-007's settings cursor. That is
# not only the "don't import another context's private helpers" rule: the two
# are not the same thing. A settings cursor encodes one unique key, while this
# one must encode the composite `(created_at, id)`, because `created_at` is not
# unique and a cursor without the tie-breaker cannot address a row
# unambiguously. Extracting a shared helper is a conversation for after VS-009
# merges, when there is a third case to generalise from.
# --------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, notification_id: UUID) -> str:
    """Opaque, URL-safe, unpadded.

    Opaque because api-endpoints.md 2.2 says "the client does not construct or
    interpret cursors" - base64 is not secrecy, it is a signal that the value is
    ours and its format may change. Padding is stripped so the cursor survives a
    query string without escaping.
    """
    raw = f"{created_at.isoformat()}{_CURSOR_SEPARATOR}{notification_id}"
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
        notification_id = UUID(id_raw)
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
    return created_at, notification_id


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


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get(
    "",
    response_model=NotificationPage,
    summary="List the authenticated user's own notifications",
    responses={
        401: {"description": "No valid session cookie was presented."},
        422: {"description": "Invalid query parameter, including a tampered cursor."},
    },
)
async def list_notifications(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    read: bool | None = Query(default=None, description="Filter by read state."),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationPage:
    """Cursor-paginated, newest first, scoped to the caller.

    `current_user` rather than the narrower `current_claims`, and the difference
    is a security one rather than a convenience. `current_claims` re-reads
    `users.auth_epoch` per ADR-018, which catches a password reset - but nothing
    bumps the epoch when an account is merely *deactivated*, so a claims-only
    dependency would keep serving a disabled account its own notifications for
    the remainder of the access token's fifteen minutes. `current_user` re-reads
    the row and re-checks `can_authenticate` (`is_active`, `anonymized_at`,
    `deleted_at`).

    That is the same reasoning VS-006 applied to `GET /me`, and notifications are
    the same kind of data: personal, and sitting under the same `/me` prefix. The
    cost is the duplicate primary-key read already recorded as a performance
    follow-up in CLAUDE.md, which is the right price for the two sibling
    endpoints agreeing about who is allowed to read.

    One extra row is fetched beyond `limit` purely to answer "is there another
    page?" without a second COUNT query; it is dropped before serialising.
    """
    rows = await NotificationRepository(session).list_page(
        user_id=user.id,
        limit=limit + 1,
        after=_decode_cursor(cursor),
        read=read,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return NotificationPage(
        items=[NotificationRead.from_notification(row) for row in page],
        next_cursor=_encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None,
    )


@router.patch(
    "/{notification_id}",
    response_model=NotificationRead,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_200_OK,
    summary="Mark one notification read or unread",
    responses={
        401: {"description": "No valid session cookie was presented."},
        403: {
            "description": (
                "CSRF token missing or invalid, or the account's email is unverified "
                "(EMAIL_VERIFICATION_REQUIRED)."
            )
        },
        404: {"description": "No such notification belongs to this user."},
        422: {"description": "Malformed request body."},
    },
)
async def set_notification_read_state(
    notification_id: UUID,
    body: NotificationUpdate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationRead:
    """Set read state, scoped to the caller by the UPDATE's own WHERE clause.

    A foreign notification and a nonexistent one produce the same 404, from the
    same code path - the statement simply affects no rows in both cases, so
    there is no branch in which the two could start to differ. That closes the
    existence oracle a 403 would open: a customer who could tell "not yours"
    from "no such thing" could enumerate other people's notification ids.
    """
    notification = await NotificationRepository(session).set_read_state(
        notification_id=notification_id,
        user_id=user.id,
        read=body.read,
    )
    if notification is None:
        raise not_found_error()
    return NotificationRead.from_notification(notification)
