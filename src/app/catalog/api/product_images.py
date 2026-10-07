"""`/api/v1/admin/products/{id}/images` (api-endpoints.md 15.2, docs/product-images.md).
Under the admin router, so `require_admin` and the admin rate limit already apply."""

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.api.product_image_schemas import (
    AltText,
    ProductImageList,
    ProductImageOrderUpdate,
    ProductImageRead,
    ProductImageUpdate,
)
from app.catalog.api.products import _translate
from app.catalog.api.reference_data import _ADMIN_RESPONSES, _audit_context
from app.catalog.application.commands.product_image_admin import (
    MAX_UPLOAD_BYTES,
    DeleteProductImage,
    ReorderProductImages,
    SetProductCover,
    UpdateProductImage,
    UploadProductImage,
)
from app.catalog.domain.exceptions import (
    ArchivedValueNotMutableError,
    CoverDeletionBlockedError,
    ImageOrderMismatchError,
    MalwareDetectedError,
    ProductImageNotFoundError,
    ProductNotFoundError,
    UploadRejectedError,
)
from app.catalog.domain.product_image import ProductImage
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.product_repository import ProductRepository
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.integrations.images.factory import get_image_sanitizer
from app.integrations.images.ports import ImageSanitizerPort
from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.ports import MalwareScannerPort, ScannerUnavailableError
from app.integrations.storage.factory import get_public_media_storage
from app.integrations.storage.ports import StoragePort
from app.platform.public import SqlAuditWriter

logger = structlog.get_logger()
admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)

# Multipart framing and the alt_text field on top of the file itself.
MULTIPART_ALLOWANCE = 64 * 1024


class BoundedUploadRoute(AdminBoundaryRoute):
    """Refuses an oversized or unsized body before it is parsed and spooled to disk."""

    async def before_body(self, request: Request) -> None:
        declared = request.headers.get("content-length")
        if declared is None or not declared.isdigit():
            raise _error(UploadRejectedError("a Content-Length header is required"))
        if int(declared) > MAX_UPLOAD_BYTES + MULTIPART_ALLOWANCE:
            raise _error(UploadRejectedError(f"an image must be at most {MAX_UPLOAD_BYTES} bytes"))


upload_router = APIRouter(tags=["admin"], route_class=BoundedUploadRoute)

IMAGES = "/products/{product_id}/images"
_ALT_TEXT: TypeAdapter[str | None] = TypeAdapter(AltText)

_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    409: {"description": "INVALID_STATE_TRANSITION: product deleted, or the cover is in use."},
    422: {"description": "UPLOAD_REJECTED, MALWARE_DETECTED or VALIDATION_ERROR."},
}
_UPLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESPONSES,
    503: {"description": "SERVICE_UNAVAILABLE: the malware scanner is down (fail closed)."},
}


def _error(exc: Exception) -> ApiError:
    if isinstance(exc, ProductImageNotFoundError | ProductNotFoundError):
        return not_found_error()
    if isinstance(exc, UploadRejectedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="UPLOAD_REJECTED",
            title="Upload rejected",
            detail=exc.reason,
            errors=[{"loc": ["body", "file"], "msg": exc.reason, "type": "value_error"}],
        )
    if isinstance(exc, MalwareDetectedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="MALWARE_DETECTED",
            title="Malware detected",
            detail="The file failed the malware scan and was not stored.",
        )
    if isinstance(exc, ScannerUnavailableError):
        return ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            title="Malware scanner unavailable",
            detail="Uploads are refused until the scanner answers; retry later.",
        )
    if isinstance(exc, ImageOrderMismatchError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            title="Image order is not valid",
            detail=str(exc),
            errors=[{"loc": ["body", "image_ids"], "msg": str(exc), "type": "value_error"}],
        )
    if isinstance(exc, CoverDeletionBlockedError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Image is the cover",
            detail=str(exc),
        )
    return _translate(exc)


_ERRORS = (
    ProductImageNotFoundError,
    ProductNotFoundError,
    UploadRejectedError,
    MalwareDetectedError,
    ScannerUnavailableError,
    ImageOrderMismatchError,
    CoverDeletionBlockedError,
    ArchivedValueNotMutableError,
)


def _read(image: ProductImage) -> ProductImageRead:
    return ProductImageRead.from_entity(image, get_settings().media_public_url)


def _stores(
    session: AsyncSession,
) -> tuple[ProductRepository, ProductImageRepository, SqlAuditWriter]:
    return ProductRepository(session), ProductImageRepository(session), SqlAuditWriter(session)


@upload_router.post(
    IMAGES,
    response_model=ProductImageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Upload a product image",
    responses=_UPLOAD_RESPONSES,
)
async def admin_upload_product_image(
    product_id: UUID,
    request: Request,
    file: UploadFile = File(
        description="JPEG, PNG or WebP, at most 10 MB; type read from content."
    ),
    alt_text: str | None = Form(default=None),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StoragePort = Depends(get_public_media_storage),
    scanner: MalwareScannerPort = Depends(get_malware_scanner),
    sanitizer: ImageSanitizerPort = Depends(get_image_sanitizer),
) -> ProductImageRead:
    try:
        clean_alt = _ALT_TEXT.validate_python(alt_text)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", "alt_text", *e["loc"])} for e in exc.errors()]
        ) from exc
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    request_id, ip_hash = _audit_context(request)
    command = UploadProductImage(
        *_stores(session), storage=storage, scanner=scanner, sanitizer=sanitizer
    )
    try:
        image = await command.execute(
            product_id=product_id,
            data=data,
            alt_text=clean_alt,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except (MalwareDetectedError, ScannerUnavailableError) as exc:
        await logger.awarning(
            "product_image_upload_refused", product_id=str(product_id), reason=type(exc).__name__
        )
        raise _error(exc) from exc
    except _ERRORS as exc:
        raise _error(exc) from exc
    return _read(image)


@admin_router.patch(
    IMAGES + "/{image_id:uuid}",
    response_model=ProductImageRead,
    dependencies=[Depends(require_csrf)],
    summary="Update a product image's alt text",
    responses=_RESPONSES,
)
async def admin_update_product_image(
    product_id: UUID,
    image_id: UUID,
    body: ProductImageUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProductImageRead:
    request_id, ip_hash = _audit_context(request)
    try:
        image = await UpdateProductImage(*_stores(session)).execute(
            product_id=product_id,
            image_id=image_id,
            alt_text=body.alt_text,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _ERRORS as exc:
        raise _error(exc) from exc
    return _read(image)


@admin_router.put(
    IMAGES + "/order",
    response_model=ProductImageList,
    dependencies=[Depends(require_csrf)],
    summary="Reorder a product's images",
    responses=_RESPONSES,
)
async def admin_reorder_product_images(
    product_id: UUID,
    body: ProductImageOrderUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProductImageList:
    request_id, ip_hash = _audit_context(request)
    try:
        images = await ReorderProductImages(*_stores(session)).execute(
            product_id=product_id,
            image_ids=body.image_ids,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _ERRORS as exc:
        raise _error(exc) from exc
    return ProductImageList(items=[_read(i) for i in images])


@admin_router.put(
    IMAGES + "/{image_id:uuid}/cover",
    response_model=ProductImageRead,
    dependencies=[Depends(require_csrf)],
    summary="Make an image the product's cover",
    responses=_RESPONSES,
)
async def admin_set_product_cover(
    product_id: UUID,
    image_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProductImageRead:
    request_id, ip_hash = _audit_context(request)
    try:
        image = await SetProductCover(*_stores(session)).execute(
            product_id=product_id,
            image_id=image_id,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _ERRORS as exc:
        raise _error(exc) from exc
    return _read(image)


@admin_router.delete(
    IMAGES + "/{image_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Soft-delete a product image",
    responses=_RESPONSES,
)
async def admin_delete_product_image(
    product_id: UUID,
    image_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    request_id, ip_hash = _audit_context(request)
    try:
        await DeleteProductImage(*_stores(session)).execute(
            product_id=product_id,
            image_id=image_id,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _ERRORS as exc:
        raise _error(exc) from exc
