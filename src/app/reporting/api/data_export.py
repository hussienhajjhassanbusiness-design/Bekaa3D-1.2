"""`GET /api/v1/me/export` (VS-044; BR-124, F-034, FR-03; ADR-046): the caller's six data
sets as one JSON document, streamed from one read-only snapshot, 3 a day, audited."""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import client_ip, get_session
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.identity.public import User, current_verified_user, require_csrf
from app.platform.public import SqlAuditWriter
from app.reporting.api.export_schemas import DataExportRead
from app.reporting.api.session import query_canceled, report_unavailable, start_snapshot
from app.reporting.application.data_export import export_sections
from app.reporting.domain.data_export import FORMAT_VERSION, ExportProfile
from app.reporting.infrastructure.export_adapters import export_sources

EXPORT_RATE_LIMIT: Final = 3
EXPORT_RATE_WINDOW_SECONDS: Final = 86_400

router = APIRouter(prefix="/me", tags=["account"])


async def _export_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user; after `current_verified_user`, so an unverified caller spends no budget."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="data_export",
        subject=str(user.id),
        limit=EXPORT_RATE_LIMIT,
        window_seconds=EXPORT_RATE_WINDOW_SECONDS,
    )


_ADAPTERS: dict[type[Any], TypeAdapter[Any]] = {}


def _json(value: Any) -> bytes:
    kind = type(value)
    if kind not in _ADAPTERS:
        _ADAPTERS[kind] = TypeAdapter(kind)
    return _ADAPTERS[kind].dump_json(value)


def export_head(profile: ExportProfile, now: datetime) -> bytes:
    """The document up to the profile; `json_chunks` appends the data sets and closes it."""
    return (
        b'{"format_version":%d,"exported_at":' % FORMAT_VERSION
        + _json(now)
        + b',"profile":'
        + _json(profile)
    )


async def json_chunks(
    head: bytes, sections: AsyncIterator[tuple[str, Sequence[object]]]
) -> AsyncIterator[bytes]:
    """One chunk per page read; the head goes out with the first, so a failed first read is
    still a clean error response."""
    pending, current, empty = head, None, True
    async for key, batch in sections:
        if key != current:
            pending += (b"]" if current is not None else b"") + b',"%s":[' % key.encode()
            current, empty = key, True
        for record in batch:
            pending += (b"" if empty else b",") + _json(record)
            empty = False
        yield pending
        pending = b""
    yield pending + (b"]" if current is not None else b"") + b"}"


async def _export_stream(
    factory: async_sessionmaker[AsyncSession], user_id: UUID, head: bytes
) -> AsyncGenerator[bytes]:
    async with factory() as session:
        await start_snapshot(session)
        async for chunk in json_chunks(head, export_sections(export_sources(session), user_id)):
            yield chunk


async def _resume(first: bytes, rest: AsyncGenerator[bytes]) -> AsyncIterator[bytes]:
    try:
        yield first
        async for chunk in rest:
            yield chunk
    finally:
        await rest.aclose()


def _profile(user: User) -> ExportProfile:
    return ExportProfile(
        id=user.id,
        email=user.email,
        role=str(user.role),
        email_verified=user.is_verified,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
    )


@router.get(
    "/export",
    response_class=StreamingResponse,
    # CSRF on a GET (ADR-046 d11): a cross-site link would otherwise spend the day's three.
    dependencies=[Depends(require_csrf), Depends(_export_rate_limit)],
    summary="Download all of the caller's own data as one JSON document",
    responses={
        200: {
            "model": DataExportRead,
            "description": "Streamed; soft-deleted addresses and reviews carry `deleted: true`.",
        },
        401: {"description": "No valid session cookie was presented."},
        403: {"description": "CSRF_INVALID, or EMAIL_VERIFICATION_REQUIRED."},
        429: {"description": "RATE_LIMITED: three exports a day per user."},
        503: {"description": "SERVICE_UNAVAILABLE: the snapshot's first read timed out."},
    },
)
async def export_my_data(
    request: Request,
    response: Response,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """The first page is read before the audit row is written, so a failed read is a 503
    with no audit row, and nothing is sent unless the audit row commits."""
    now = datetime.now(UTC)
    chunks = _export_stream(
        request.app.state.db_session_factory, user.id, export_head(_profile(user), now)
    )
    try:
        first = await anext(chunks)
    except DBAPIError as exc:
        if query_canceled(exc):
            raise report_unavailable() from exc
        raise
    ip = client_ip(request)
    try:
        await SqlAuditWriter(session).record(
            actor_user_id=user.id,
            action="user.data_exported",
            entity_type="user",
            entity_id=user.id,
            after_data={"format_version": FORMAT_VERSION},
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except BaseException:
        await chunks.aclose()
        raise
    limits = {k: v for k, v in response.headers.items() if k.lower().startswith("ratelimit-")}
    filename = f"bekaa3d-data-export-{now:%Y%m%d}.json"
    return StreamingResponse(
        _resume(first, chunks),
        media_type="application/json",
        headers={
            **limits,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
