"""Customer reviews (VS-036, api-endpoints.md 14.1). Writes need a verified email, CSRF
and the shared write limit; the public list is per-IP limited. Badges are masked (D14)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.public import reviewable_products, visible_product
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit, rate_limiter
from app.engagement.api.review_cursor import decode_review_cursor, encode_review_cursor
from app.engagement.api.review_schemas import (
    MyReviewPage,
    MyReviewRead,
    PublicReviewRead,
    ReviewCreate,
    ReviewPage,
    ReviewUpdate,
)
from app.engagement.application.services.reviews import (
    create_review,
    delete_review,
    edit_review,
)
from app.engagement.domain.exceptions import (
    ReviewAlreadyExistsError,
    ReviewContentRejectedError,
    ReviewNotFoundError,
    ReviewProductUnavailableError,
)
from app.engagement.domain.review_limits import (
    REVIEW_READ_LIMIT,
    REVIEW_READ_WINDOW_SECONDS,
    REVIEW_WRITE_LIMIT,
    REVIEW_WRITE_WINDOW_SECONDS,
)
from app.engagement.domain.reviews import Review, badge_shown
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)
from app.ordering.public import purchase_evidence

public_router = APIRouter(tags=["reviews"])
me_router = APIRouter(prefix="/me/reviews", tags=["reviews"])
router = APIRouter(prefix="/reviews", tags=["reviews"])

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 50

_PUBLIC_LIMIT = rate_limiter(
    key_prefix="reviews_public",
    limit=REVIEW_READ_LIMIT,
    window_seconds=REVIEW_READ_WINDOW_SECONDS,
)
_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    422: {"description": "Validation failed, or REVIEW_CONTENT_REJECTED (with `reason`)."},
    429: {"description": "RATE_LIMITED: too many review changes this hour."},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No live review of yours with this id."}
}


async def _write_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """After `current_verified_user`, so anonymous callers never spend the budget. One
    bucket for POST, PATCH and DELETE (VS-036 plan 5)."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="reviews",
        subject=str(user.id),
        limit=REVIEW_WRITE_LIMIT,
        window_seconds=REVIEW_WRITE_WINDOW_SECONDS,
    )


def _translate(exc: Exception) -> ApiError:
    if isinstance(exc, ReviewAlreadyExistsError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="REVIEW_ALREADY_EXISTS",
            title="Review already exists",
            detail="You already have a review of this product.",
        )
    if isinstance(exc, ReviewContentRejectedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="REVIEW_CONTENT_REJECTED",
            title="Review content rejected",
            detail="The review text contains a link or a word that is not allowed.",
            extensions={"reason": exc.reason},
        )
    return not_found_error()


async def _mine(session: AsyncSession, review: Review) -> MyReviewRead:
    product = (await reviewable_products(session, [review.product_id])).get(review.product_id)
    mode = product.purchase_mode if product is not None else None
    return MyReviewRead.mine(review, product, shown=badge_shown(review.is_verified_purchase, mode))


@public_router.get(
    "/products/{slug}/reviews",
    response_model=ReviewPage,
    dependencies=[Depends(_PUBLIC_LIMIT)],
    summary="List a visible product's reviews",
    responses={
        404: {"description": "Unknown, deleted or non-public product."},
        429: {"description": "RATE_LIMITED."},
    },
)
async def list_product_reviews(
    slug: str,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    rating: int | None = Query(default=None, ge=1, le=5),
    verified_purchase: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ReviewPage:
    """Visible reviews, newest first. A WhatsApp-only product never shows the badge (D14),
    so `verified_purchase=true` is empty there and `false` returns every row."""
    after = decode_review_cursor(cursor)
    product = await visible_product(session, slug)
    if product is None:
        raise not_found_error()
    masked = not badge_shown(True, product.purchase_mode)
    if masked and verified_purchase:
        return ReviewPage(items=[], next_cursor=None)
    rows = await SqlReviewStore(session).public_page(
        product.id,
        rating=rating,
        verified=None if masked else verified_purchase,
        after=after,
        limit=limit + 1,
    )
    page = rows[:limit]
    return ReviewPage(
        items=[
            PublicReviewRead.of(
                row, shown=badge_shown(row.is_verified_purchase, product.purchase_mode)
            )
            for row in page
        ],
        next_cursor=encode_review_cursor(page[-1]) if len(rows) > limit else None,
    )


@me_router.get(
    "",
    response_model=MyReviewPage,
    summary="List the authenticated user's own reviews",
    responses=_READ_RESPONSES,
)
async def list_my_reviews(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MyReviewPage:
    """Live reviews, hidden ones included with `is_hidden`, newest first."""
    rows = await SqlReviewStore(session).own_page(
        user.id, after=decode_review_cursor(cursor), limit=limit + 1
    )
    page = rows[:limit]
    products = await reviewable_products(session, [row.product_id for row in page])
    items = []
    for row in page:
        product = products.get(row.product_id)
        mode = product.purchase_mode if product is not None else None
        shown = badge_shown(row.is_verified_purchase, mode)
        items.append(MyReviewRead.mine(row, product, shown=shown))
    return MyReviewPage(
        items=items, next_cursor=encode_review_cursor(page[-1]) if len(rows) > limit else None
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=MyReviewRead,
    dependencies=[Depends(_write_rate_limit), Depends(require_csrf)],
    summary="Review a product (one live review per product)",
    responses={
        **_WRITE_RESPONSES,
        404: {"description": "Unknown, deleted or non-public product."},
        409: {"description": "REVIEW_ALREADY_EXISTS: a live review exists, hidden or not."},
    },
)
async def post_review(
    body: ReviewCreate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> MyReviewRead:
    try:
        review = await create_review(
            SqlReviewStore(session),
            CatalogReviewableProducts(session),
            purchase_evidence(session),
            user_id=user.id,
            product_id=body.product_id,
            rating=body.rating,
            body=body.body,
        )
    except (
        ReviewAlreadyExistsError,
        ReviewContentRejectedError,
        ReviewProductUnavailableError,
    ) as exc:
        raise _translate(exc) from exc
    return await _mine(session, review)


@router.patch(
    "/{review_id}",
    response_model=MyReviewRead,
    dependencies=[Depends(_write_rate_limit), Depends(require_csrf)],
    summary="Edit your own review (a hidden review stays hidden)",
    responses={**_WRITE_RESPONSES, **_NOT_FOUND},
)
async def patch_review(
    review_id: UUID,
    body: ReviewUpdate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> MyReviewRead:
    try:
        review = await edit_review(
            SqlReviewStore(session),
            CatalogReviewableProducts(session),
            purchase_evidence(session),
            user_id=user.id,
            review_id=review_id,
            rating=body.rating,
            body=body.body,
            body_given="body" in body.model_fields_set,
        )
    except (ReviewContentRejectedError, ReviewNotFoundError) as exc:
        raise _translate(exc) from exc
    return await _mine(session, review)


@router.delete(
    "/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(_write_rate_limit), Depends(require_csrf)],
    summary="Delete your own review (soft delete)",
    responses={**_WRITE_RESPONSES, **_NOT_FOUND},
)
async def remove_review(
    review_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await delete_review(
            SqlReviewStore(session),
            CatalogReviewableProducts(session),
            user_id=user.id,
            review_id=review_id,
        )
    except ReviewNotFoundError as exc:
        raise _translate(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
