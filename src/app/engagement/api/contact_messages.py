"""Contact form and admin queue (VS-033, FR-16). Public POST order: attempt limit, body,
captcha, then per-IP and per-email limits, so a refused captcha spends neither quota."""

import base64
import binascii
import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.captcha import CAPTCHA_RESPONSES, require_captcha
from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit, rate_limiter
from app.core.security import hash_ip
from app.engagement.api.contact_message_schemas import (
    ContactMessageAdminUpdate,
    ContactMessageCreate,
    ContactMessageDetail,
    ContactMessagePage,
    ContactMessageReceipt,
)
from app.engagement.application.commands.change_contact_message_status import (
    ENTITY_TYPE,
    ChangeContactMessageStatus,
)
from app.engagement.application.commands.submit_contact_message import SubmitContactMessage
from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.domain.exceptions import (
    ContactMessageNotFoundError,
    InvalidContactMessageTransitionError,
)
from app.engagement.infrastructure.contact_messages import SqlContactMessageRepository
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.integrations.captcha.factory import get_captcha_verifier
from app.integrations.captcha.ports import CaptchaPort
from app.platform.public import SqlAuditWriter

public_router = APIRouter(prefix="/contact-messages", tags=["contact"])
logger = structlog.get_logger()
admin_router = APIRouter(prefix="/contact-messages", tags=["admin"], route_class=AdminBoundaryRoute)

WINDOW_SECONDS = 3600
# Before the captcha, so a flood of bad tokens cannot buy unlimited Cloudflare calls.
ATTEMPT_LIMIT = 60
IP_LIMIT = 5
EMAIL_LIMIT = 5
_ATTEMPT_LIMIT = rate_limiter(
    key_prefix="contact:attempt", limit=ATTEMPT_LIMIT, window_seconds=WINDOW_SECONDS
)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_CURSOR_SEPARATOR = "|"

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown message id, or caller is not an administrator."},
}


@public_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ContactMessageReceipt,
    dependencies=[Depends(_ATTEMPT_LIMIT)],
    summary="Send a message to the business",
    responses={
        **CAPTCHA_RESPONSES,
        422: {"description": "A field is missing or invalid; nothing is stored."},
        429: {"description": "Rate limit exceeded."},
    },
)
async def submit_contact_message(
    body: ContactMessageCreate,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    captcha: CaptchaPort = Depends(get_captcha_verifier),
) -> ContactMessageReceipt:
    await require_captcha(body.captcha_token, captcha)
    details = body.details()
    await enforce_rate_limit(
        request,
        response,
        key_prefix="contact:ip",
        subject=request.client.host if request.client else "unknown",
        limit=IP_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )
    await enforce_rate_limit(
        request,
        response,
        key_prefix="contact:email",
        # Hashed, as the login throttle does, so Redis holds no list of addresses.
        subject=hashlib.sha256(details.email.lower().encode("utf-8")).hexdigest()[:32],
        limit=EMAIL_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )
    message = await SubmitContactMessage(SqlContactMessageRepository(session)).execute(details)
    # The id only: the sender and body are PII and are never logged (VS-033).
    await logger.ainfo("contact_message_received", contact_message_id=str(message.id))
    return ContactMessageReceipt(id=message.id, created_at=message.created_at)


def _encode_cursor(state: ContactMessageStatus, created_at: datetime, message_id: UUID) -> str:
    raw = _CURSOR_SEPARATOR.join((state.value, created_at.isoformat(), str(message_id)))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str) -> tuple[ContactMessageStatus, datetime, UUID]:
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
        state_raw, created_raw, id_raw = decoded.split(_CURSOR_SEPARATOR)
        parsed = ContactMessageStatus(state_raw), datetime.fromisoformat(created_raw), UUID(id_raw)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if not _is_utc_representable(parsed[1]):
        raise ValueError("cursor is not a valid pagination cursor")
    return parsed


def _is_utc_representable(moment: datetime) -> bool:
    """Aware and convertible to UTC; asyncpg overflowed on the rest (BUG-36)."""
    if moment.tzinfo is None:
        return False
    try:
        moment.astimezone(UTC)
    except OverflowError:
        return False
    return True


def _invalid(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


def _decode_cursor(raw: str | None) -> tuple[ContactMessageStatus, datetime, UUID] | None:
    if raw is None:
        return None
    try:
        return _parse_cursor(raw)
    except ValueError as exc:
        raise _invalid("cursor", str(exc)) from exc


def _check_range(created_after: datetime | None, created_before: datetime | None) -> None:
    for field, moment in (("created_after", created_after), ("created_before", created_before)):
        if moment is not None and not _is_utc_representable(moment):
            raise _invalid(field, "must be a timestamp with a UTC offset, e.g. 2026-10-01T00:00Z")
    if created_after is not None and created_before is not None and created_before <= created_after:
        raise _invalid("created_before", "must be later than created_after")


def _audit_context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


@admin_router.get(
    "",
    response_model=ContactMessagePage,
    summary="List the contact message queue",
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "Invalid query parameter, a tampered cursor or an empty range."},
    },
)
async def list_contact_messages(
    request: Request,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    status_filter: ContactMessageStatus | None = Query(default=None, alias="status"),
    created_after: datetime | None = Query(
        default=None, description="Inclusive lower bound; must carry a UTC offset."
    ),
    created_before: datetime | None = Query(
        default=None, description="Exclusive upper bound; must carry a UTC offset."
    ),
    email: str | None = Query(
        default=None, max_length=254, description="Exact, case-insensitive sender address."
    ),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ContactMessagePage:
    """New first, then oldest first. Audited like the user list, since it shows PII."""
    after = _decode_cursor(cursor)
    _check_range(created_after, created_before)
    rows = await SqlContactMessageRepository(session).list_page(
        limit=limit + 1,
        after=after,
        status=status_filter,
        created_after=created_after,
        created_before=created_before,
        email=email,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="contact_message.list_viewed",
        entity_type=ENTITY_TYPE,
        entity_id=None,
        after_data={
            "filters": {
                "status": status_filter.value if status_filter else None,
                "created_after": bool(created_after),
                "created_before": bool(created_before),
                "email": bool(email),
            },
            "result_count": len(page),
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    last = page[-1] if has_more and page else None
    return ContactMessagePage(
        items=[ContactMessageDetail.of(row) for row in page],
        next_cursor=_encode_cursor(last.status, last.created_at, last.id) if last else None,
    )


@admin_router.get(
    "/{message_id}",
    response_model=ContactMessageDetail,
    summary="Read one contact message",
    responses=_ADMIN_RESPONSES,
)
async def read_contact_message(
    message_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ContactMessageDetail:
    """Audited as `contact_message.viewed`; reading does not mark it read."""
    message = await SqlContactMessageRepository(session).get(message_id)
    if message is None:
        raise not_found_error()
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="contact_message.viewed",
        entity_type=ENTITY_TYPE,
        entity_id=message.id,
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return ContactMessageDetail.of(message)


@admin_router.patch(
    "/{message_id}",
    response_model=ContactMessageDetail,
    dependencies=[Depends(require_csrf)],
    summary="Move a contact message forward in the queue",
    responses={
        **_ADMIN_RESPONSES,
        403: {"description": "CSRF token missing or invalid."},
        409: {"description": "`INVALID_STATE_TRANSITION` - status may only move forward."},
        422: {"description": "Malformed body or unknown status."},
    },
)
async def update_contact_message(
    message_id: UUID,
    body: ContactMessageAdminUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ContactMessageDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        message = await ChangeContactMessageStatus(
            SqlContactMessageRepository(session), SqlAuditWriter(session)
        ).execute(
            message_id=message_id,
            status=body.status,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ContactMessageNotFoundError as exc:
        raise not_found_error() from exc
    except InvalidContactMessageTransitionError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Contact message status cannot move backwards",
            detail=f"A {exc.current} message cannot become {exc.target}.",
        ) from exc
    return ContactMessageDetail.of(message)
