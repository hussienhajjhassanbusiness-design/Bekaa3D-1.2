"""`/api/v1/admin/products` (api-endpoints.md 15.1, docs/products.md). Mounted
under the admin router, so `require_admin` and the admin rate limit already apply."""

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.api.product_schemas import (
    AdminProductCreate,
    AdminProductDetail,
    AdminProductPage,
    AdminProductUpdate,
)
from app.catalog.api.reference_data import (
    _ADMIN_RESPONSES,
    _archived_error,
    _audit_context,
    _invalid_slug_error,
    _slug_conflict_error,
)
from app.catalog.application.commands.product_admin import (
    CreateProduct,
    DeleteProduct,
    UpdateProduct,
)
from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import (
    ArchivedValueNotMutableError,
    InvalidSlugError,
    ProductNotFoundError,
    ProductValidationError,
    ReferenceValueUnusableError,
    SlugConflictError,
    VersionConflictError,
)
from app.catalog.domain.product import Product
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.product_repository import (
    ProductFilter,
    ProductRepository,
    ProductSort,
)
from app.catalog.infrastructure.repositories import SqlReferenceLocks
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.text import has_control_characters
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_MAX_QUERY_LENGTH = 200

_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    409: {"description": "SLUG_CONFLICT, VERSION_CONFLICT or INVALID_STATE_TRANSITION."},
    422: {"description": "VALIDATION_ERROR, including physical/STL type integrity."},
}

# Fields named in a type-integrity error that the request spells differently.
_REQUEST_FIELD = {"price_cents": "price", "currency": "price"}


def _validation_error(errors: dict[str, str]) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        title="Product is not valid",
        detail="; ".join(f"{field}: {reason}" for field, reason in errors.items()),
        errors=[
            {
                "loc": ["body", *_REQUEST_FIELD.get(field, field).split(".")],
                "msg": reason,
                "type": "value_error",
            }
            for field, reason in errors.items()
        ],
    )


def _version_conflict_error(exc: VersionConflictError) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="VERSION_CONFLICT",
        title="Product was changed by someone else",
        detail=f"The product is at version {exc.current_version}; re-read it and retry.",
        extensions={"current_version": exc.current_version},
    )


def _translate(exc: Exception) -> ApiError:
    """Domain error -> stable API error; anything unknown is re-raised by the caller."""
    if isinstance(exc, ProductNotFoundError):
        return not_found_error()
    if isinstance(exc, ProductValidationError):
        return _validation_error(exc.errors)
    if isinstance(exc, ReferenceValueUnusableError):
        return _validation_error({exc.field: "must name a category/material/colour not archived"})
    if isinstance(exc, InvalidSlugError):
        return _invalid_slug_error(exc)
    if isinstance(exc, SlugConflictError):
        return _slug_conflict_error(exc)
    if isinstance(exc, VersionConflictError):
        return _version_conflict_error(exc)
    if isinstance(exc, ArchivedValueNotMutableError):
        return _archived_error(exc)
    raise exc


_DOMAIN_ERRORS = (
    ProductNotFoundError,
    ProductValidationError,
    ReferenceValueUnusableError,
    InvalidSlugError,
    SlugConflictError,
    VersionConflictError,
    ArchivedValueNotMutableError,
)


async def _detail(session: AsyncSession, product: Product) -> AdminProductDetail:
    images = await ProductImageRepository(session).live_for_product(product.id)
    return AdminProductDetail.from_entity(product, images, get_settings().media_public_url)


def _encode_cursor(sort: str, product: AdminProductDetail) -> str:
    key: Any = (
        product.created_at.isoformat() if sort == "-created_at" else product.price.amount_cents
    )
    raw = json.dumps({"s": sort, "k": key, "i": str(product.id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode("ascii").rstrip("=")


def _bad_query(name: str, message: str) -> RequestValidationError:
    return RequestValidationError([{"loc": ("query", name), "msg": message, "type": "value_error"}])


def _decode_cursor(raw: str | None, sort: str) -> tuple[int | datetime, UUID] | None:
    """Strict: a cursor from another sort, or any malformed field, is a 422."""
    if raw is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if not isinstance(payload, dict) or payload.get("s") != sort:
            raise ValueError
        key, product_id = payload["k"], UUID(payload["i"])
        if sort == "-created_at":
            parsed = datetime.fromisoformat(key)
            if parsed.tzinfo is None:
                raise ValueError
            return parsed, product_id
        if type(key) is not int:
            raise ValueError
        return key, product_id
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError) as exc:
        raise _bad_query("cursor", "cursor is not a valid pagination cursor") from exc


@admin_router.get(
    "/products",
    response_model=AdminProductPage,
    summary="List products",
    responses=_ADMIN_RESPONSES,
)
async def admin_list_products(
    type: ProductType | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    is_visible: bool | None = Query(default=None),
    is_featured: bool | None = Query(default=None),
    is_available: bool | None = Query(default=None),
    deleted: bool = Query(default=False, description="true lists only soft-deleted products."),
    q: str | None = Query(default=None, min_length=1, max_length=_MAX_QUERY_LENGTH),
    sort: ProductSort = Query(default="-created_at"),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
) -> AdminProductPage:
    if q is not None and has_control_characters(q):
        raise _bad_query("q", "must not contain control characters")
    filters = ProductFilter(
        product_type=type,
        category_id=category_id,
        is_visible=is_visible,
        is_featured=is_featured,
        is_available=is_available,
        deleted=deleted,
        q=q,
    )
    rows = await ProductRepository(session).list_page(
        limit=limit + 1, sort=sort, filters=filters, after=_decode_cursor(cursor, sort)
    )
    images = await ProductImageRepository(session).live_for_products(r.id for r in rows[:limit])
    media = get_settings().media_public_url
    page = [AdminProductDetail.from_entity(r, images[r.id], media) for r in rows[:limit]]
    has_more = len(rows) > limit
    return AdminProductPage(
        items=page, next_cursor=_encode_cursor(sort, page[-1]) if has_more and page else None
    )


@admin_router.post(
    "/products",
    response_model=AdminProductDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a product",
    responses=_WRITE_RESPONSES,
)
async def admin_create_product(
    body: AdminProductCreate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminProductDetail:
    request_id, ip_hash = _audit_context(request)
    command = CreateProduct(
        ProductRepository(session), SqlReferenceLocks(session), SqlAuditWriter(session)
    )
    try:
        product = await command.execute(
            product_type=body.type,
            attributes=body.to_attributes(),
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _DOMAIN_ERRORS as exc:
        raise _translate(exc) from exc
    return AdminProductDetail.from_entity(product, [], get_settings().media_public_url)


@admin_router.get(
    "/products/{product_id}",
    response_model=AdminProductDetail,
    summary="Read one product",
    responses=_ADMIN_RESPONSES,
)
async def admin_read_product(
    product_id: UUID, session: AsyncSession = Depends(get_session)
) -> AdminProductDetail:
    product = await ProductRepository(session).get_by_id(product_id)
    if product is None:
        raise not_found_error()
    return await _detail(session, product)


@admin_router.patch(
    "/products/{product_id}",
    response_model=AdminProductDetail,
    dependencies=[Depends(require_csrf)],
    summary="Update a product",
    responses=_WRITE_RESPONSES,
)
async def admin_update_product(
    product_id: UUID,
    body: AdminProductUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminProductDetail:
    request_id, ip_hash = _audit_context(request)
    command = UpdateProduct(
        ProductRepository(session), SqlReferenceLocks(session), SqlAuditWriter(session)
    )
    try:
        result = await command.execute(
            product_id=product_id,
            expected_version=body.version,
            changes=body.changes(),
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _DOMAIN_ERRORS as exc:
        raise _translate(exc) from exc
    return await _detail(session, result.product)


@admin_router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Soft-delete a product",
    responses=_WRITE_RESPONSES,
)
async def admin_delete_product(
    product_id: UUID,
    request: Request,
    version: int = Query(ge=1, description="The version last read (ADR-020)."),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    request_id, ip_hash = _audit_context(request)
    command = DeleteProduct(
        ProductRepository(session), SqlReferenceLocks(session), SqlAuditWriter(session)
    )
    try:
        await command.execute(
            product_id=product_id,
            expected_version=version,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except _DOMAIN_ERRORS as exc:
        raise _translate(exc) from exc
