"""Bring Your Idea submission (VS-034, FR-15, ADR-030). Order: attempt limit and body size
before parsing, fields, file count and sizes, captcha, per-IP and per-email limits, then the
ADR-021 pipeline per file, storage and insert. No auth cookies or CSRF: guests submit."""

import hashlib
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.captcha import CAPTCHA_RESPONSES, require_captcha
from app.api.dependencies import get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.engagement.api.custom_request_schemas import CustomRequestCreate, CustomRequestReceipt
from app.engagement.application.commands.submit_custom_request import (
    AttachmentUpload,
    SubmitCustomRequest,
)
from app.engagement.domain.custom_request import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    check_attachment_count,
    check_attachment_size,
)
from app.engagement.domain.exceptions import AttachmentMalwareError, AttachmentRejectedError
from app.engagement.infrastructure.administrators import IdentityAdministratorDirectory
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.engagement.infrastructure.repositories import SavepointNotificationRepository
from app.integrations.captcha.factory import get_captcha_verifier
from app.integrations.captcha.ports import CaptchaPort
from app.integrations.images.factory import get_image_sanitizer
from app.integrations.images.ports import ImageSanitizerPort
from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.ports import MalwareScannerPort, ScannerUnavailableError
from app.integrations.storage.factory import get_private_upload_storage
from app.integrations.storage.ports import StoragePort
from app.platform.public import settings_reader

logger = structlog.get_logger()

WINDOW_SECONDS = 3600
# Before the body is parsed, as one attempt may carry 50 MB (ADR-030).
ATTEMPT_LIMIT = 20
IP_LIMIT = 5
EMAIL_LIMIT = 5
# Multipart framing and the text fields on top of the files themselves.
MULTIPART_ALLOWANCE = 64 * 1024
MAX_BODY_BYTES = MAX_ATTACHMENTS * MAX_ATTACHMENT_BYTES + MULTIPART_ALLOWANCE
RETENTION_KEY = "custom_request_attachment_retention"


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _upload_rejected(reason: str, index: int | None = None) -> ApiError:
    loc: list[str | int] = ["body", "attachments"] + ([index] if index is not None else [])
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="UPLOAD_REJECTED",
        title="Upload rejected",
        detail=reason,
        errors=[{"loc": loc, "msg": reason, "type": "value_error"}],
    )


class BoundedPublicUploadRoute(APIRoute):
    """Spends an attempt and refuses an oversized or unsized body before it is spooled."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            await enforce_rate_limit(
                request,
                Response(),
                key_prefix="custom_request:attempt",
                subject=_client(request),
                limit=ATTEMPT_LIMIT,
                window_seconds=WINDOW_SECONDS,
            )
            declared = request.headers.get("content-length")
            if declared is None or not declared.isdigit():
                raise _upload_rejected("a Content-Length header is required")
            if int(declared) > MAX_BODY_BYTES:
                raise _upload_rejected(f"a request must be at most {MAX_BODY_BYTES} bytes")
            return await handler(request)

        return guarded


public_router = APIRouter(
    prefix="/custom-requests", tags=["custom requests"], route_class=BoundedPublicUploadRoute
)


def _fields(**values: Any) -> CustomRequestCreate:
    try:
        return CustomRequestCreate.model_validate(values)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from exc


@public_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomRequestReceipt,
    summary="Submit a Bring Your Idea request",
    responses={
        **CAPTCHA_RESPONSES,
        422: {"description": "VALIDATION_ERROR, UPLOAD_REJECTED or MALWARE_DETECTED."},
        429: {"description": "Rate limit exceeded."},
        503: {"description": "SERVICE_UNAVAILABLE: captcha or malware scanner unavailable."},
    },
)
async def submit_custom_request(
    request: Request,
    response: Response,
    name: str = Form(),
    email: str = Form(),
    phone: str = Form(),
    project_title: str = Form(),
    description: str = Form(),
    preferred_material: str | None = Form(default=None),
    preferred_colour: str | None = Form(default=None),
    dimensions: str | None = Form(default=None),
    captcha_token: str = Form(),
    attachments: list[UploadFile] = File(
        default=[],
        description="0-5 JPEG, PNG or WebP images, each at most 10 MB; type read from content.",
    ),
    session: AsyncSession = Depends(get_session),
    captcha: CaptchaPort = Depends(get_captcha_verifier),
    storage: StoragePort = Depends(get_private_upload_storage),
    scanner: MalwareScannerPort = Depends(get_malware_scanner),
    sanitizer: ImageSanitizerPort = Depends(get_image_sanitizer),
) -> CustomRequestReceipt:
    body = _fields(
        name=name,
        email=email,
        phone=phone,
        project_title=project_title,
        description=description,
        preferred_material=preferred_material,
        preferred_colour=preferred_colour,
        dimensions=dimensions,
        captcha_token=captcha_token,
    )
    details = body.details()
    files = attachments
    try:
        check_attachment_count(len(files))
        for index, file in enumerate(files):
            check_attachment_size(index, file.size or 0)
    except AttachmentRejectedError as exc:
        raise _upload_rejected(exc.reason, exc.index) from exc

    await require_captcha(body.captcha_token, captcha)
    await enforce_rate_limit(
        request,
        response,
        key_prefix="custom_request:ip",
        subject=_client(request),
        limit=IP_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )
    await enforce_rate_limit(
        request,
        response,
        key_prefix="custom_request:email",
        # Hashed, as the contact form does, so Redis holds no list of addresses.
        subject=hashlib.sha256(details.email.lower().encode("utf-8")).hexdigest()[:32],
        limit=EMAIL_LIMIT,
        window_seconds=WINDOW_SECONDS,
    )

    uploads = [AttachmentUpload(f.filename, await f.read(MAX_ATTACHMENT_BYTES + 1)) for f in files]
    retention = await settings_reader(session).get_duration_seconds(RETENTION_KEY)
    command = SubmitCustomRequest(
        SqlCustomRequestRepository(session),
        SavepointNotificationRepository(session),
        IdentityAdministratorDirectory(session),
        storage=storage,
        scanner=scanner,
        sanitizer=sanitizer,
    )
    try:
        submission = await command.execute(details, uploads, retention_seconds=retention)
    except AttachmentRejectedError as exc:
        raise _upload_rejected(exc.reason, exc.index) from exc
    except AttachmentMalwareError as exc:
        await logger.awarning("custom_request_upload_refused", reason="malware", index=exc.index)
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="MALWARE_DETECTED",
            title="Malware detected",
            detail="An attachment failed the malware scan; nothing was stored.",
            errors=[{"loc": ["body", "attachments", exc.index], "msg": "malware detected"}],
        ) from exc
    except ScannerUnavailableError as exc:
        await logger.awarning("custom_request_upload_refused", reason="scanner_unavailable")
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            title="Malware scanner unavailable",
            detail="Uploads are refused until the scanner answers; retry later.",
        ) from exc
    created = submission.request
    if submission.failed_notifications:
        await logger.aerror(
            "custom_request_notification_failed",
            custom_request_id=str(created.id),
            failed=submission.failed_notifications,
        )
    # Ids and a count only: the visitor's details are PII and are never logged.
    await logger.ainfo(
        "custom_request_received",
        custom_request_id=str(created.id),
        attachment_count=len(created.attachments),
    )
    return CustomRequestReceipt(id=created.id, created_at=created.created_at)
