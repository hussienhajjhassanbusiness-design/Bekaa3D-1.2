"""The administrator's Bring Your Idea pipeline (VS-035, FR-15, ADR-031). Every route sits
behind the admin boundary; reads that show visitor PII are audited like the contact queue."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.security import hash_ip
from app.engagement.api.custom_request_schemas import (
    CustomRequestAdminUpdate,
    CustomRequestDetail,
    CustomRequestPage,
    CustomRequestSummary,
    CustomRequestTransition,
)
from app.engagement.api.queue_cursor import check_range, decode_cursor, encode_cursor
from app.engagement.application.commands.custom_request_pipeline import (
    ENTITY_TYPE,
    AdminContext,
    OpenCustomRequestAttachment,
    TransitionCustomRequest,
    UpdateCustomRequestNotes,
)
from app.engagement.domain.custom_request import download_filename
from app.engagement.domain.enums import CustomRequestStatus
from app.engagement.domain.exceptions import (
    CustomRequestAttachmentNotFoundError,
    CustomRequestNotFoundError,
    InvalidCustomRequestTransitionError,
)
from app.engagement.infrastructure.custom_requests import SqlCustomRequestPipelineRepository
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.integrations.storage.factory import get_private_upload_storage
from app.integrations.storage.ports import StoragePort
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/custom-requests", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
# The bytes are a re-encoded image, but are still served as inert, never-cached data.
_DOWNLOAD_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
}

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown id, or caller is not an administrator."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    403: {"description": "CSRF token missing or invalid."},
    422: {"description": "Malformed body."},
}


def _context(request: Request, claims: AccessTokenClaims) -> AdminContext:
    ip = client_ip(request)
    return AdminContext(
        actor_user_id=claims.user_id,
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(ip) if ip else None,
    )


def _content_disposition(filename: str) -> str:
    """An ASCII fallback plus RFC 6266 `filename*`, so no visitor text breaks the header."""
    fallback = "".join(c if c.isascii() and c not in '"\\' else "_" for c in filename)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@admin_router.get(
    "",
    response_model=CustomRequestPage,
    summary="List the Bring Your Idea pipeline",
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "Invalid query parameter, a tampered cursor or an empty range."},
    },
)
async def list_custom_requests(
    request: Request,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    status_filter: CustomRequestStatus | None = Query(default=None, alias="status"),
    created_after: datetime | None = Query(
        default=None, description="Inclusive lower bound; must carry a UTC offset."
    ),
    created_before: datetime | None = Query(
        default=None, description="Exclusive upper bound; must carry a UTC offset."
    ),
    email: str | None = Query(
        default=None, max_length=254, description="Exact, case-insensitive visitor address."
    ),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CustomRequestPage:
    """Pipeline order, `new` first then oldest first; `closed` and `lost` come last."""
    after = decode_cursor(cursor, CustomRequestStatus)
    check_range(created_after, created_before)
    rows = await SqlCustomRequestPipelineRepository(session).list_page(
        limit=limit + 1,
        after=after,
        status=status_filter,
        created_after=created_after,
        created_before=created_before,
        email=email,
        now=datetime.now(UTC),
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    context = _context(request, claims)
    await SqlAuditWriter(session).record(
        actor_user_id=context.actor_user_id,
        action="custom_request.list_viewed",
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
        request_id=context.request_id,
        ip_hash=context.ip_hash,
    )
    last = page[-1] if has_more and page else None
    return CustomRequestPage(
        items=[CustomRequestSummary.of(row) for row in page],
        next_cursor=encode_cursor(last.status, last.created_at, last.id) if last else None,
    )


@admin_router.get(
    "/{request_id}",
    response_model=CustomRequestDetail,
    summary="Read one Bring Your Idea request",
    responses=_ADMIN_RESPONSES,
)
async def read_custom_request(
    request_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CustomRequestDetail:
    """Lists only attachments that have not expired; audited as `custom_request.viewed`."""
    lead = await SqlCustomRequestPipelineRepository(session).get(request_id, now=datetime.now(UTC))
    if lead is None:
        raise not_found_error()
    context = _context(request, claims)
    await SqlAuditWriter(session).record(
        actor_user_id=context.actor_user_id,
        action="custom_request.viewed",
        entity_type=ENTITY_TYPE,
        entity_id=lead.id,
        request_id=context.request_id,
        ip_hash=context.ip_hash,
    )
    return CustomRequestDetail.of(lead)


@admin_router.patch(
    "/{request_id}",
    response_model=CustomRequestDetail,
    dependencies=[Depends(require_csrf)],
    summary="Edit a request's admin notes",
    responses=_WRITE_RESPONSES,
)
async def update_custom_request(
    request_id: UUID,
    body: CustomRequestAdminUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CustomRequestDetail:
    """Status is not editable here; `extra=forbid` makes a `status` field a 422."""
    command = UpdateCustomRequestNotes(
        SqlCustomRequestPipelineRepository(session), SqlAuditWriter(session)
    )
    try:
        lead = await command.execute(
            custom_request_id=request_id,
            admin_notes=body.notes(),
            now=datetime.now(UTC),
            context=_context(request, claims),
        )
    except CustomRequestNotFoundError as exc:
        raise not_found_error() from exc
    return CustomRequestDetail.of(lead)


@admin_router.post(
    "/{request_id}/transition",
    response_model=CustomRequestDetail,
    dependencies=[Depends(require_csrf)],
    summary="Move a request along the pipeline",
    responses={
        **_WRITE_RESPONSES,
        409: {"description": "`INVALID_STATE_TRANSITION` - not an edge of the pipeline."},
        422: {"description": "Malformed body, or a quote missing, out of range or misplaced."},
    },
)
async def transition_custom_request(
    request_id: UUID,
    body: CustomRequestTransition,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CustomRequestDetail:
    command = TransitionCustomRequest(
        SqlCustomRequestPipelineRepository(session), SqlAuditWriter(session)
    )
    try:
        lead = await command.execute(
            custom_request_id=request_id,
            target=body.target_status,
            quoted_amount_cents=body.quoted_amount_cents,
            now=datetime.now(UTC),
            context=_context(request, claims),
        )
    except CustomRequestNotFoundError as exc:
        raise not_found_error() from exc
    except InvalidCustomRequestTransitionError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Custom request cannot make this transition",
            detail=f"A {exc.current} request cannot become {exc.target}.",
        ) from exc
    return CustomRequestDetail.of(lead)


@admin_router.get(
    "/{request_id}/attachments/{attachment_id}/download",
    response_class=StreamingResponse,
    summary="Download a private reference image",
    responses={
        200: {"description": "The stored image, as an attachment.", "content": {"image/*": {}}},
        **_ADMIN_RESPONSES,
    },
)
async def download_custom_request_attachment(
    request_id: UUID,
    attachment_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StoragePort = Depends(get_private_upload_storage),
) -> StreamingResponse:
    """Streamed by the API until VS-020 may hand it to nginx `X-Accel-Redirect` (ADR-031).
    No Range support: images are at most 10 MB. Expired or missing files are 404."""
    command = OpenCustomRequestAttachment(
        SqlCustomRequestPipelineRepository(session), storage, SqlAuditWriter(session)
    )
    try:
        attachment, stream = await command.execute(
            custom_request_id=request_id,
            attachment_id=attachment_id,
            now=datetime.now(UTC),
            context=_context(request, claims),
        )
    except CustomRequestAttachmentNotFoundError as exc:
        raise not_found_error() from exc
    filename = download_filename(attachment.original_filename, attachment.mime_type)
    headers = _DOWNLOAD_HEADERS | {
        "Content-Disposition": _content_disposition(filename),
        "Content-Length": str(stream.size),
    }
    return StreamingResponse(stream.chunks, media_type=attachment.mime_type, headers=headers)
