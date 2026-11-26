"""Seasonal promotions (app.catalog.domain.promotions).

Admin, under the admin router (administrator + MFA; a customer gets 404):
  GET   /api/v1/admin/promotions           newest first, at most 200
  POST  /api/v1/admin/promotions           CSRF; 201
  GET   /api/v1/admin/promotions/{id}
  PATCH /api/v1/admin/promotions/{id}      CSRF; partial; `active` switches it on/off
Public:
  GET   /api/v1/promotions                 the promotions active now (banner data)

There is no delete: an administrator switches a promotion off (`active: false`) or lets it
end, and the audit log keeps the history. Every write is audited."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.api.promotion_schemas import (
    AdminPromotionCreate,
    AdminPromotionList,
    AdminPromotionRead,
    AdminPromotionUpdate,
    PublicPromotionList,
    PublicPromotionRead,
)
from app.catalog.api.reference_data import (
    _ADMIN_RESPONSES,
    PUBLIC_RATE_LIMIT,
    PUBLIC_RATE_WINDOW_SECONDS,
    _audit_context,
)
from app.catalog.domain.promotions import (
    Promotion,
    PromotionFields,
    PromotionScope,
    normalized,
    validate_promotion,
)
from app.catalog.infrastructure.promotion_repository import SqlPromotions
from app.core.exceptions import ApiError
from app.core.rate_limit import rate_limiter
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)
public_router = APIRouter(tags=["catalogue"])

_PUBLIC_LIMIT = rate_limiter(
    key_prefix="catalogue:promotions",
    limit=PUBLIC_RATE_LIMIT,
    window_seconds=PUBLIC_RATE_WINDOW_SECONDS,
)
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    403: {"description": "CSRF_INVALID."},
    422: {"description": "VALIDATION_ERROR: a broken promotion rule, named per field."},
}


def _validation_error(errors: dict[str, str]) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        title="Promotion is not valid",
        detail="; ".join(f"{field}: {reason}" for field, reason in errors.items()),
        errors=[
            {"loc": ["body", field], "msg": reason, "type": "value_error"}
            for field, reason in errors.items()
        ],
    )


async def _checked(promotions: SqlPromotions, fields: PromotionFields) -> PromotionFields:
    clean = normalized(fields)
    errors = validate_promotion(clean)
    if clean.scope is PromotionScope.SELECTED and "product_ids" not in errors:
        missing = clean.product_ids - await promotions.live_product_ids(clean.product_ids)
        if missing:
            errors["product_ids"] = "must name existing, not deleted products"
    if errors:
        raise _validation_error(errors)
    return clean


def _audit_data(promotion: Promotion) -> dict[str, Any]:
    f = promotion.fields
    return {
        "name": f.name,
        "badge_text": f.badge_text,
        "discount_type": f.discount_type.value,
        "discount_value": f.discount_value,
        "scope": f.scope.value,
        "product_ids": sorted(str(i) for i in f.product_ids),
        "starts_at": f.starts_at.isoformat(),
        "ends_at": f.ends_at.isoformat(),
        "active": f.active,
    }


@admin_router.get(
    "/promotions",
    response_model=AdminPromotionList,
    summary="List promotions",
    responses=_ADMIN_RESPONSES,
)
async def admin_list_promotions(session: AsyncSession = Depends(get_session)) -> AdminPromotionList:
    now = datetime.now(UTC)
    rows = await SqlPromotions(session).list_recent()
    return AdminPromotionList(items=[AdminPromotionRead.of(p, now) for p in rows])


@admin_router.post(
    "/promotions",
    response_model=AdminPromotionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a promotion",
    responses=_WRITE_RESPONSES,
)
async def admin_create_promotion(
    body: AdminPromotionCreate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminPromotionRead:
    now = datetime.now(UTC)
    promotions = SqlPromotions(session)
    fields = await _checked(promotions, body.to_fields())
    created = await promotions.create(fields, now)
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="promotion.created",
        entity_type="promotion",
        entity_id=created.id,
        after_data=_audit_data(created),
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return AdminPromotionRead.of(created, now)


@admin_router.get(
    "/promotions/{promotion_id}",
    response_model=AdminPromotionRead,
    summary="Read one promotion",
    responses=_ADMIN_RESPONSES,
)
async def admin_read_promotion(
    promotion_id: UUID, session: AsyncSession = Depends(get_session)
) -> AdminPromotionRead:
    found = await SqlPromotions(session).get(promotion_id)
    if found is None:
        raise not_found_error()
    return AdminPromotionRead.of(found, datetime.now(UTC))


@admin_router.patch(
    "/promotions/{promotion_id}",
    response_model=AdminPromotionRead,
    dependencies=[Depends(require_csrf)],
    summary="Update a promotion, or switch it on or off",
    responses=_WRITE_RESPONSES,
)
async def admin_update_promotion(
    promotion_id: UUID,
    body: AdminPromotionUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminPromotionRead:
    now = datetime.now(UTC)
    promotions = SqlPromotions(session)
    current = await promotions.get(promotion_id, for_update=True)
    if current is None:
        raise not_found_error()
    fields = await _checked(promotions, body.merged(current.fields))
    if fields == current.fields:
        return AdminPromotionRead.of(current, now)
    updated = await promotions.update(current, fields, now)
    request_id, ip_hash = _audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="promotion.updated",
        entity_type="promotion",
        entity_id=updated.id,
        before_data=_audit_data(current),
        after_data=_audit_data(updated),
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return AdminPromotionRead.of(updated, now)


@public_router.get(
    "/promotions",
    response_model=PublicPromotionList,
    dependencies=[Depends(_PUBLIC_LIMIT)],
    summary="The promotions active now",
    responses={429: {"description": "RATE_LIMITED."}},
)
async def list_active_promotions(
    session: AsyncSession = Depends(get_session),
) -> PublicPromotionList:
    active = await SqlPromotions(session).active_at(datetime.now(UTC))
    return PublicPromotionList(items=[PublicPromotionRead.of(p) for p in active])
