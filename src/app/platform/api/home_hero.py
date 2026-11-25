"""The homepage hero image (docs/homepage-hero-image.md).

Admin, under the admin router (administrator + MFA; a customer gets 404):
  PUT  /api/v1/admin/home/hero-image    CSRF; multipart `file`; replaces the image
Public:
  GET  /api/v1/home/hero-image          {"url": ...}, null while the default visual shows

The value lives in the `homepage_hero_image` setting (a storage key the upload generates),
so it is audited like every setting and an administrator restores the default visual with
`PATCH /api/v1/admin/settings/homepage_hero_image {"value": null}`. The public read is a
separate endpoint, not a field of `GET /settings/public`, whose fixed schema is its
security design; it returns a URL, never the key."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.catalog.public import media_url
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import rate_limiter
from app.core.security import hash_ip
from app.identity.public import AccessTokenClaims, AdminBoundaryRoute, require_admin, require_csrf
from app.integrations.images.factory import get_image_sanitizer
from app.integrations.images.ports import ImageSanitizerPort
from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.ports import MalwareScannerPort, ScannerUnavailableError
from app.integrations.storage.factory import get_public_media_storage
from app.integrations.storage.ports import StoragePort
from app.platform.application.commands.replace_hero_image import (
    MAX_HERO_IMAGE_BYTES,
    ReplaceHeroImage,
)
from app.platform.domain.exceptions import (
    HeroImageMalwareError,
    HeroImageRejectedError,
    InvalidSettingValueError,
)
from app.platform.domain.settings_registry import HOMEPAGE_HERO_IMAGE_KEY, validate_value
from app.platform.infrastructure.repositories import AuditLogRepository, SettingRepository

logger = structlog.get_logger()

# Multipart framing on top of the file itself (the product-image allowance).
MULTIPART_ALLOWANCE = 64 * 1024
HERO_IMAGE = "/home/hero-image"


def _rejected(reason: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="UPLOAD_REJECTED",
        title="Upload rejected",
        detail=reason,
        errors=[{"loc": ["body", "file"], "msg": reason, "type": "value_error"}],
    )


class _BoundedUploadRoute(AdminBoundaryRoute):
    """Refuses an oversized or unsized body before it is parsed and spooled to disk."""

    async def before_body(self, request: Request) -> None:
        declared = request.headers.get("content-length")
        if declared is None or not declared.isdigit():
            raise _rejected("a Content-Length header is required")
        if int(declared) > MAX_HERO_IMAGE_BYTES + MULTIPART_ALLOWANCE:
            raise _rejected(f"an image must be at most {MAX_HERO_IMAGE_BYTES} bytes")


upload_router = APIRouter(tags=["admin"], route_class=_BoundedUploadRoute)
public_router = APIRouter(tags=["settings"])

# Read on every homepage load, like the public settings: the same allowance.
_PUBLIC_LIMIT = rate_limiter(key_prefix="home:hero", limit=600, window_seconds=3600)


class HeroImageRead(BaseModel):
    url: str | None = Field(
        description="The uploaded hero image, or null while the default brand visual shows."
    )


def _read(key: str | None) -> HeroImageRead:
    return HeroImageRead(url=media_url(get_settings().media_public_url, key) if key else None)


@upload_router.put(
    HERO_IMAGE,
    response_model=HeroImageRead,
    dependencies=[Depends(require_csrf)],
    summary="Replace the homepage hero image",
    responses={
        401: {"description": "No session, or MFA not completed."},
        403: {"description": "CSRF_INVALID."},
        404: {"description": "Caller is not an administrator."},
        422: {"description": "UPLOAD_REJECTED or MALWARE_DETECTED; the current image stays."},
        503: {"description": "SERVICE_UNAVAILABLE: the malware scanner is down (fail closed)."},
    },
)
async def admin_replace_hero_image(
    request: Request,
    file: UploadFile = File(
        description="JPEG, PNG or WebP, at most 10 MB and at least 400 px on each side; "
        "type read from content."
    ),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StoragePort = Depends(get_public_media_storage),
    scanner: MalwareScannerPort = Depends(get_malware_scanner),
    sanitizer: ImageSanitizerPort = Depends(get_image_sanitizer),
) -> HeroImageRead:
    data = await file.read(MAX_HERO_IMAGE_BYTES + 1)
    ip = client_ip(request)
    command = ReplaceHeroImage(
        SettingRepository(session),
        AuditLogRepository(session),
        storage=storage,
        scanner=scanner,
        sanitizer=sanitizer,
    )
    try:
        key = await command.execute(
            data=data,
            actor_user_id=claims.user_id,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except HeroImageRejectedError as exc:
        raise _rejected(exc.reason) from exc
    except HeroImageMalwareError as exc:
        await logger.awarning("hero_image_upload_refused", reason="malware")
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="MALWARE_DETECTED",
            title="Malware detected",
            detail="The file failed the malware scan and was not stored.",
        ) from exc
    except ScannerUnavailableError as exc:
        await logger.awarning("hero_image_upload_refused", reason="scanner_unavailable")
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            title="Malware scanner unavailable",
            detail="Uploads are refused until the scanner answers; retry later.",
        ) from exc
    return _read(key)


@public_router.get(
    HERO_IMAGE,
    response_model=HeroImageRead,
    dependencies=[Depends(_PUBLIC_LIMIT)],
    summary="The homepage hero image",
    responses={429: {"description": "RATE_LIMITED."}},
)
async def read_hero_image(session: AsyncSession = Depends(get_session)) -> HeroImageRead:
    """A missing or unusable row reads as the default visual: the hero is decoration, and a
    broken value must never take the homepage down with it."""
    setting = await SettingRepository(session).get_by_key(HOMEPAGE_HERO_IMAGE_KEY)
    key: Any = None if setting is None else setting.value
    try:
        key = validate_value(HOMEPAGE_HERO_IMAGE_KEY, key)
    except InvalidSettingValueError:
        await logger.awarning("hero_image_setting_unusable")
        key = None
    return _read(key if isinstance(key, str) else None)
