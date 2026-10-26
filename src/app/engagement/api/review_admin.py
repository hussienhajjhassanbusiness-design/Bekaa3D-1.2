"""The administrator's review moderation (VS-037, BR-106, api-endpoints.md 22). Behind the
admin boundary; writes need CSRF. Reads show no PII and are not audited (Q4)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.catalog.public import reviewable_products
from app.core.exceptions import ApiError
from app.core.security import hash_ip
from app.engagement.api.review_admin_schemas import (
    AdminReviewDetail,
    AdminReviewPage,
    AdminReviewRead,
    ReviewModerationRequest,
)
from app.engagement.api.review_cursor import decode_review_cursor, encode_review_cursor
from app.engagement.application.commands.custom_request_pipeline import AdminContext
from app.engagement.application.services.review_moderation import moderate_review
from app.engagement.domain.exceptions import ReviewModerationConflictError, ReviewNotFoundError
from app.engagement.domain.reviews import RATING_MAX, RATING_MIN, Review
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/reviews", tags=["admin"], route_class=AdminBoundaryRoute)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

_ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Unknown or deleted review, or caller is not an administrator."},
    429: {"description": "RATE_LIMITED: the admin router's per-administrator limit."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ADMIN_RESPONSES,
    403: {"description": "CSRF token missing or invalid."},
    409: {"description": "INVALID_STATE_TRANSITION: already in that state; carries is_hidden."},
    422: {"description": "Malformed body, or a reason over 500 characters."},
}


def _context(request: Request, claims: AccessTokenClaims) -> AdminContext:
    ip = client_ip(request)
    return AdminContext(
        actor_user_id=claims.user_id,
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(ip) if ip else None,
    )


async def _detail(session: AsyncSession, review: Review) -> AdminReviewDetail:
    product = (await reviewable_products(session, [review.product_id])).get(review.product_id)
    return AdminReviewDetail(**AdminReviewRead.of(review, product).model_dump())


@admin_router.get(
    "",
    response_model=AdminReviewPage,
    summary="List live reviews for moderation, newest first",
    responses={**_ADMIN_RESPONSES, 422: {"description": "Invalid query or tampered cursor."}},
)
async def list_reviews(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    hidden: bool | None = Query(default=None),
    rating: int | None = Query(default=None, ge=RATING_MIN, le=RATING_MAX),
    product_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    verified_purchase: bool | None = Query(
        default=None, description="Filters the stored evidence flag, not the masked badge."
    ),
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminReviewPage:
    """Soft-deleted reviews never appear (D3); hidden and visible ones both do."""
    rows = await SqlReviewStore(session).admin_page(
        hidden=hidden,
        rating=rating,
        product_id=product_id,
        user_id=user_id,
        verified=verified_purchase,
        after=decode_review_cursor(cursor),
        limit=limit + 1,
    )
    page = rows[:limit]
    products = await reviewable_products(session, [row.product_id for row in page])
    return AdminReviewPage(
        items=[AdminReviewRead.of(row, products.get(row.product_id)) for row in page],
        next_cursor=encode_review_cursor(page[-1]) if len(rows) > limit else None,
    )


@admin_router.get(
    "/{review_id}",
    response_model=AdminReviewDetail,
    summary="Read one live review with its moderation state",
    responses=_ADMIN_RESPONSES,
)
async def read_review(
    review_id: UUID,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminReviewDetail:
    review = await SqlReviewStore(session).live_by_id(review_id)
    if review is None:
        raise not_found_error()
    return await _detail(session, review)


async def _moderate(
    review_id: UUID,
    body: ReviewModerationRequest | None,
    request: Request,
    claims: AccessTokenClaims,
    session: AsyncSession,
    *,
    hide: bool,
) -> AdminReviewDetail:
    try:
        review = await moderate_review(
            SqlReviewStore(session),
            CatalogReviewableProducts(session),
            SqlAuditWriter(session),
            review_id=review_id,
            hide=hide,
            reason=body.reason if body is not None else None,
            now=datetime.now(UTC),
            context=_context(request, claims),
        )
    except ReviewNotFoundError as exc:
        raise not_found_error() from exc
    except ReviewModerationConflictError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Review is already hidden" if exc.is_hidden else "Review is not hidden",
            detail=str(exc),
            extensions={"is_hidden": exc.is_hidden},
        ) from exc
    return await _detail(session, review)


@admin_router.post(
    "/{review_id}/hide",
    response_model=AdminReviewDetail,
    dependencies=[Depends(require_csrf)],
    summary="Hide a review; recomputes the product's rating in the same transaction",
    responses=_WRITE_RESPONSES,
)
async def hide_review(
    review_id: UUID,
    request: Request,
    body: ReviewModerationRequest | None = None,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminReviewDetail:
    return await _moderate(review_id, body, request, claims, session, hide=True)


@admin_router.post(
    "/{review_id}/restore",
    response_model=AdminReviewDetail,
    dependencies=[Depends(require_csrf)],
    summary="Restore a hidden review; recomputes the product's rating in the same transaction",
    responses=_WRITE_RESPONSES,
)
async def restore_review(
    review_id: UUID,
    request: Request,
    body: ReviewModerationRequest | None = None,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminReviewDetail:
    return await _moderate(review_id, body, request, claims, session, hide=False)
