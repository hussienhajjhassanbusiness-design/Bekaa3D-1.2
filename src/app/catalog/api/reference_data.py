"""Public reference lists and the admin CRUD surface for catalogue facets.

Two routers, deliberately separate. The admin one is mounted inside
`/api/v1/admin`, whose router-level `require_admin` already enforces
authenticated + administrator + MFA-complete (VS-005), so nothing here
re-implements authorization. The public one is unauthenticated, rate limited,
and returns hard-limited lists rather than cursor pages.
"""

import base64
import binascii
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.catalog.api.schemas import (
    AdminCategoryPage,
    AdminColourPage,
    AdminMaterialPage,
    CategoryCreate,
    CategoryDetail,
    CategoryList,
    CategoryRead,
    CategoryUpdate,
    ColourCreate,
    ColourDetail,
    ColourList,
    ColourRead,
    ColourUpdate,
    MaterialCreate,
    MaterialDetail,
    MaterialList,
    MaterialRead,
    MaterialUpdate,
)
from app.catalog.application.commands.category_admin import (
    ArchiveCategory,
    CreateCategory,
    UpdateCategory,
)
from app.catalog.application.commands.value_admin import (
    ArchiveReferenceValue,
    CreateReferenceValue,
    UpdateReferenceValue,
)
from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.exceptions import (
    ArchivedValueNotMutableError,
    InvalidSlugError,
    NameConflictError,
    ReferenceValueInUseError,
    ReferenceValueNotFoundError,
    SlugConflictError,
)
from app.catalog.infrastructure.repositories import (
    CategoryRepository,
    ColourRepository,
    MaterialRepository,
)
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
from app.platform.public import SqlAuditWriter

public_router = APIRouter(tags=["catalogue"])
admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)

# api-endpoints.md calls these "hard-limited reference list" without giving a
# number. 100 is a V1 product decision recorded in docs/reference-data.md: it is
# far more categories/materials/colours than this catalogue will carry, and it
# bounds the response without the client needing to paginate a facet list.
PUBLIC_LIST_LIMIT = 100

# The endpoint catalogue lists 429 for these routes but gives no policy. 600/hour
# per IP is the same starting figure adopted for public settings in VS-007, and
# for the same reason: these are read on ordinary page loads, so the allowance
# has to be generous enough that no human browsing reaches it. A V1 operational
# decision, not an SRS number. Each endpoint gets its own counter, so exhausting
# one does not refuse the others.
PUBLIC_RATE_LIMIT = 600
PUBLIC_RATE_WINDOW_SECONDS = 3600

_CATEGORIES_LIMIT = rate_limiter(
    key_prefix="catalogue:categories",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)
_MATERIALS_LIMIT = rate_limiter(
    key_prefix="catalogue:materials",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)
_COLOURS_LIMIT = rate_limiter(
    key_prefix="catalogue:colours",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


# --------------------------------------------------------------------------
# Cursor
#
# Local to Catalog. VS-007 kept its settings cursor local and VS-008 kept its
# notifications cursor local; this is the third, and extracting a shared helper
# is a conversation for after VS-009 merges rather than something to do while
# two slices are in flight.
#
# The payload is base64 of JSON rather than a delimited string. Ordering is by
# `(name, id)` and a name is arbitrary administrator text - it may contain any
# character, including whatever delimiter looked safe - so a `"name|id"` cursor
# would be ambiguous for perfectly ordinary input.
# --------------------------------------------------------------------------


def _encode_cursor(name: str, value_id: UUID) -> str:
    raw = json.dumps({"n": name, "i": str(value_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str | None) -> tuple[str, UUID] | None:
    """Decode a cursor into its `(name, id)` pair, or raise `ValueError`.

    Every field is parsed strictly. A cursor that decoded into a half-valid pair
    would not fail loudly - it would silently page from the wrong place.
    """
    if raw is None:
        return None
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc

    if not isinstance(payload, dict):
        raise ValueError("cursor is not a valid pagination cursor")
    name = payload.get("n")
    identifier = payload.get("i")
    if not isinstance(name, str) or not isinstance(identifier, str):
        raise ValueError("cursor is not a valid pagination cursor")
    try:
        return name, UUID(identifier)
    except ValueError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc


def _decode_cursor(raw: str | None) -> tuple[str, UUID] | None:
    """Decode at the point of use, and report a bad cursor the usual way.

    Explicitly not attached to the query parameter as a Pydantic
    `AfterValidator`: FastAPI did not apply one in VS-007, so a tampered cursor
    was used verbatim and pagination never terminated.
    """
    try:
        decoded = _parse_cursor(raw)
        # The name becomes a query parameter, and PostgreSQL cannot take NUL:
        # it reached asyncpg and answered 500 (BUG-03). Checked here, not in
        # `_parse_cursor`, which stays a faithful inverse of `_encode_cursor`.
        if decoded is not None and "\x00" in decoded[0]:
            raise ValueError("cursor is not a valid pagination cursor")
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": str(exc), "type": "value_error"}]
        ) from exc
    return decoded


# --------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------


def _slug_conflict_error(exc: SlugConflictError) -> ApiError:
    """409 SLUG_CONFLICT (api-endpoints.md 186: "Live slug already exists")."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="SLUG_CONFLICT",
        title="Slug already in use",
        detail=f"Another live {exc.entity_type.lower()} already uses the slug {exc.slug!r}.",
    )


def _name_conflict_error(exc: NameConflictError) -> ApiError:
    """409 SLUG_CONFLICT for a material/colour name already live (any case).

    Deliberately the existing code, not a new `NAME_CONFLICT`: the error
    catalogue is a contract, and for a client the situation is the same one -
    the identifier-like value it chose is taken by a live row, so choose
    another. `title`/`detail` say which value collided.
    """
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="SLUG_CONFLICT",
        title="Name already in use",
        detail=(
            f"Another live {exc.entity_type.lower()} already uses the name {exc.name!r} "
            "(names are compared case-insensitively)."
        ),
    )


def _archived_error(exc: ArchivedValueNotMutableError) -> ApiError:
    """409 INVALID_STATE_TRANSITION.

    Reusing the catalogue's existing generic state-machine code rather than
    inventing one: "requested state-machine transition is illegal"
    (api-endpoints.md 182) describes archiving-then-editing exactly, and the
    error catalogue is a contract rather than a place to add synonyms.
    """
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Value is archived",
        detail=f"{exc.entity_type} {exc.entity_id} is archived and can no longer be modified.",
    )


def _invalid_slug_error(exc: InvalidSlugError) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        title="Slug is not valid",
        detail=exc.reason,
        errors=[{"loc": ["body", "slug"], "msg": exc.reason, "type": "value_error"}],
    )


def _in_use_error(exc: ReferenceValueInUseError) -> ApiError:
    """The slice plan's single code for all three resources, not only categories."""
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="CATEGORY_IN_USE",
        title="Value is in use",
        detail=f"{exc.entity_type} {exc.entity_id} is used by a live product; reassign it first.",
    )


def _audit_context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


# --------------------------------------------------------------------------
# Public endpoints
#
# Every one filters on `deleted_at IS NULL AND is_active = true`, and the
# response schemas carry only id/name(/slug). Two independent guards, both of
# which would have to be removed for a disabled or archived value to appear.
# --------------------------------------------------------------------------

_PUBLIC_RESPONSES: dict[int | str, dict[str, Any]] = {429: {"description": "Rate limit exceeded."}}


@public_router.get(
    "/categories",
    response_model=CategoryList,
    dependencies=[Depends(_CATEGORIES_LIMIT)],
    summary="List active categories",
    responses=_PUBLIC_RESPONSES,
)
async def list_public_categories(session: AsyncSession = Depends(get_session)) -> CategoryList:
    rows = await CategoryRepository(session).list_public(limit=PUBLIC_LIST_LIMIT)
    return CategoryList(items=[CategoryRead.from_entity(row) for row in rows])


@public_router.get(
    "/materials",
    response_model=MaterialList,
    dependencies=[Depends(_MATERIALS_LIMIT)],
    summary="List active materials",
    responses=_PUBLIC_RESPONSES,
)
async def list_public_materials(session: AsyncSession = Depends(get_session)) -> MaterialList:
    rows = await MaterialRepository(session).list_public(limit=PUBLIC_LIST_LIMIT)
    return MaterialList(items=[MaterialRead.from_entity(row) for row in rows])


@public_router.get(
    "/colours",
    response_model=ColourList,
    dependencies=[Depends(_COLOURS_LIMIT)],
    summary="List active colours",
    responses=_PUBLIC_RESPONSES,
)
async def list_public_colours(session: AsyncSession = Depends(get_session)) -> ColourList:
    rows = await ColourRepository(session).list_public(limit=PUBLIC_LIST_LIMIT)
    return ColourList(items=[ColourRead.from_entity(row) for row in rows])


# --------------------------------------------------------------------------
# Admin: categories
# --------------------------------------------------------------------------

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown id, or caller is not an administrator."},
}
_ARCHIVE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    409: {"description": "CATEGORY_IN_USE or INVALID_STATE_TRANSITION (already archived)."},
}


@admin_router.get("/categories", response_model=AdminCategoryPage, summary="List categories")
async def admin_list_categories(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    include_deleted: bool = Query(default=False, description="Include archived rows."),
    session: AsyncSession = Depends(get_session),
) -> AdminCategoryPage:
    rows = await CategoryRepository(session).list_page(
        limit=limit + 1, after=_decode_cursor(cursor), include_deleted=include_deleted
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return AdminCategoryPage(
        items=[CategoryDetail.from_entity(row) for row in page],
        next_cursor=_encode_cursor(page[-1].name, page[-1].id) if has_more and page else None,
    )


@admin_router.post(
    "/categories",
    response_model=CategoryDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a category",
    responses=_ADMIN_RESPONSES,
)
async def admin_create_category(
    body: CategoryCreate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CategoryDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        category = await CreateCategory(
            CategoryRepository(session), SqlAuditWriter(session)
        ).execute(
            name=body.name,
            slug=body.slug,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except InvalidSlugError as exc:
        raise _invalid_slug_error(exc) from exc
    except SlugConflictError as exc:
        raise _slug_conflict_error(exc) from exc
    return CategoryDetail.from_entity(category)


@admin_router.get(
    "/categories/{category_id}",
    response_model=CategoryDetail,
    summary="Read one category",
    responses=_ADMIN_RESPONSES,
)
async def admin_read_category(
    category_id: UUID, session: AsyncSession = Depends(get_session)
) -> CategoryDetail:
    category = await CategoryRepository(session).get_by_id(category_id)
    if category is None:
        raise not_found_error()
    return CategoryDetail.from_entity(category)


@admin_router.patch(
    "/categories/{category_id}",
    response_model=CategoryDetail,
    dependencies=[Depends(require_csrf)],
    summary="Update a category",
    responses=_ADMIN_RESPONSES,
)
async def admin_update_category(
    category_id: UUID,
    body: CategoryUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CategoryDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        result = await UpdateCategory(CategoryRepository(session), SqlAuditWriter(session)).execute(
            category_id=category_id,
            name=body.name,
            slug=body.slug,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except InvalidSlugError as exc:
        raise _invalid_slug_error(exc) from exc
    except SlugConflictError as exc:
        raise _slug_conflict_error(exc) from exc
    return CategoryDetail.from_entity(result.category)


@admin_router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Archive a category",
    responses=_ARCHIVE_RESPONSES,
)
async def admin_archive_category(
    category_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    request_id, ip_hash = _audit_context(request)
    try:
        await ArchiveCategory(CategoryRepository(session), SqlAuditWriter(session)).execute(
            category_id=category_id,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except ReferenceValueInUseError as exc:
        raise _in_use_error(exc) from exc


# --------------------------------------------------------------------------
# Admin: materials and colours
#
# Written out per resource rather than generated, because each is a distinct
# public API path; the *logic* behind them is shared by the parameterised
# commands in `value_admin`.
# --------------------------------------------------------------------------


@admin_router.get("/materials", response_model=AdminMaterialPage, summary="List materials")
async def admin_list_materials(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    include_deleted: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> AdminMaterialPage:
    rows = await MaterialRepository(session).list_page(
        limit=limit + 1, after=_decode_cursor(cursor), include_deleted=include_deleted
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return AdminMaterialPage(
        items=[MaterialDetail.from_entity(row) for row in page],
        next_cursor=_encode_cursor(page[-1].name, page[-1].id) if has_more and page else None,
    )


@admin_router.post(
    "/materials",
    response_model=MaterialDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a material",
    responses=_ADMIN_RESPONSES,
)
async def admin_create_material(
    body: MaterialCreate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MaterialDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        value = await CreateReferenceValue[Material](
            MaterialRepository(session), SqlAuditWriter(session), entity_type="Material"
        ).execute(
            name=body.name,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except NameConflictError as exc:
        raise _name_conflict_error(exc) from exc
    return MaterialDetail.from_entity(value)


@admin_router.get(
    "/materials/{material_id}",
    response_model=MaterialDetail,
    summary="Read one material",
    responses=_ADMIN_RESPONSES,
)
async def admin_read_material(
    material_id: UUID, session: AsyncSession = Depends(get_session)
) -> MaterialDetail:
    value = await MaterialRepository(session).get_by_id(material_id)
    if value is None:
        raise not_found_error()
    return MaterialDetail.from_entity(value)


@admin_router.patch(
    "/materials/{material_id}",
    response_model=MaterialDetail,
    dependencies=[Depends(require_csrf)],
    summary="Update a material",
    responses=_ADMIN_RESPONSES,
)
async def admin_update_material(
    material_id: UUID,
    body: MaterialUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MaterialDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        result = await UpdateReferenceValue[Material](
            MaterialRepository(session), SqlAuditWriter(session), entity_type="Material"
        ).execute(
            value_id=material_id,
            name=body.name,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except NameConflictError as exc:
        raise _name_conflict_error(exc) from exc
    return MaterialDetail.from_entity(result.value)


@admin_router.delete(
    "/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Archive a material",
    responses=_ARCHIVE_RESPONSES,
)
async def admin_archive_material(
    material_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    request_id, ip_hash = _audit_context(request)
    try:
        await ArchiveReferenceValue[Material](
            MaterialRepository(session), SqlAuditWriter(session), entity_type="Material"
        ).execute(
            value_id=material_id,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except ReferenceValueInUseError as exc:
        raise _in_use_error(exc) from exc


@admin_router.get("/colours", response_model=AdminColourPage, summary="List colours")
async def admin_list_colours(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    include_deleted: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> AdminColourPage:
    rows = await ColourRepository(session).list_page(
        limit=limit + 1, after=_decode_cursor(cursor), include_deleted=include_deleted
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return AdminColourPage(
        items=[ColourDetail.from_entity(row) for row in page],
        next_cursor=_encode_cursor(page[-1].name, page[-1].id) if has_more and page else None,
    )


@admin_router.post(
    "/colours",
    response_model=ColourDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a colour",
    responses=_ADMIN_RESPONSES,
)
async def admin_create_colour(
    body: ColourCreate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ColourDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        value = await CreateReferenceValue[Colour](
            ColourRepository(session), SqlAuditWriter(session), entity_type="Colour"
        ).execute(
            name=body.name,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except NameConflictError as exc:
        raise _name_conflict_error(exc) from exc
    return ColourDetail.from_entity(value)


@admin_router.get(
    "/colours/{colour_id}",
    response_model=ColourDetail,
    summary="Read one colour",
    responses=_ADMIN_RESPONSES,
)
async def admin_read_colour(
    colour_id: UUID, session: AsyncSession = Depends(get_session)
) -> ColourDetail:
    value = await ColourRepository(session).get_by_id(colour_id)
    if value is None:
        raise not_found_error()
    return ColourDetail.from_entity(value)


@admin_router.patch(
    "/colours/{colour_id}",
    response_model=ColourDetail,
    dependencies=[Depends(require_csrf)],
    summary="Update a colour",
    responses=_ADMIN_RESPONSES,
)
async def admin_update_colour(
    colour_id: UUID,
    body: ColourUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ColourDetail:
    request_id, ip_hash = _audit_context(request)
    try:
        result = await UpdateReferenceValue[Colour](
            ColourRepository(session), SqlAuditWriter(session), entity_type="Colour"
        ).execute(
            value_id=colour_id,
            name=body.name,
            is_active=body.is_active,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except NameConflictError as exc:
        raise _name_conflict_error(exc) from exc
    return ColourDetail.from_entity(result.value)


@admin_router.delete(
    "/colours/{colour_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Archive a colour",
    responses=_ARCHIVE_RESPONSES,
)
async def admin_archive_colour(
    colour_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    request_id, ip_hash = _audit_context(request)
    try:
        await ArchiveReferenceValue[Colour](
            ColourRepository(session), SqlAuditWriter(session), entity_type="Colour"
        ).execute(
            value_id=colour_id,
            actor_user_id=claims.user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReferenceValueNotFoundError as exc:
        raise not_found_error() from exc
    except ArchivedValueNotMutableError as exc:
        raise _archived_error(exc) from exc
    except ReferenceValueInUseError as exc:
        raise _in_use_error(exc) from exc
