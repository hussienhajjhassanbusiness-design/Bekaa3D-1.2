"""The customer's own wishlist (VS-038, FR-14, api-endpoints.md 14.2). Reading needs
only a session; adding/removing need a verified email, CSRF, and a shared rate limit."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import Product, ProductStore
from app.catalog.public import product_store
from app.core.rate_limit import enforce_rate_limit
from app.engagement.api.schemas import WishlistItemRead, WishlistPage
from app.engagement.application.services.wishlist import add_to_wishlist, remove_from_wishlist
from app.engagement.domain.exceptions import WishlistProductUnavailableError
from app.engagement.infrastructure.wishlist import SqlWishlistCounter, SqlWishlistRepository
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)

router = APIRouter(prefix="/me/wishlist", tags=["wishlist"])

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_CURSOR_SEPARATOR = "|"

_RATE_LIMIT = 120
_RATE_WINDOW_SECONDS = 3600

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    429: {"description": "RATE_LIMITED: too many wishlist changes this hour."},
}


# --------------------------------------------------------------------------
# Cursor - local to this endpoint, same shape as notifications.py's, since
# the sort here is fixed to (-created_at, id) with no second dimension.
# --------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, product_id: UUID) -> str:
    raw = f"{created_at.isoformat()}{_CURSOR_SEPARATOR}{product_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    created_raw, separator, id_raw = decoded.partition(_CURSOR_SEPARATOR)
    if not separator:
        raise ValueError("cursor is not a valid pagination cursor")
    try:
        created_at = datetime.fromisoformat(created_raw)
        product_id = UUID(id_raw)
    except ValueError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if created_at.tzinfo is None:
        raise ValueError("cursor is not a valid pagination cursor")
    try:
        created_at.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    return created_at, product_id


def _decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    try:
        return _parse_cursor(raw)
    except ValueError as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": str(exc), "type": "value_error"}]
        ) from exc


async def _wishlist_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Depends on `current_verified_user` itself, so an anonymous or
    unverified caller never consumes the budget (same ordering trick as
    `admin_rate_limit`). One shared bucket for PUT and DELETE - add/remove
    churn on the same product is one abuse shape, not two."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="wishlist",
        subject=str(user.id),
        limit=_RATE_LIMIT,
        window_seconds=_RATE_WINDOW_SECONDS,
    )


@router.get(
    "",
    response_model=WishlistPage,
    summary="List the authenticated user's own wishlist",
    responses=_READ_RESPONSES,
)
async def list_wishlist(
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    products: ProductStore = Depends(product_store),
) -> WishlistPage:
    """Active items only, newest first. One extra row is fetched beyond
    `limit` purely to answer "is there another page?". The page's product
    ids are resolved in one batched call, not one lookup per item."""
    rows = await SqlWishlistRepository(session).list_page(
        user_id=user.id, after=_decode_cursor(cursor), limit=limit + 1
    )
    has_more = len(rows) > limit
    page = rows[:limit]

    found = await products.get_many([item.product_id for item in page])
    by_id: dict[UUID, Product] = {product.id: product for product in found}

    return WishlistPage(
        items=[WishlistItemRead.of(item, by_id.get(item.product_id)) for item in page],
        next_cursor=_encode_cursor(page[-1].created_at, page[-1].product_id)
        if has_more and page
        else None,
    )


@router.put(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(_wishlist_rate_limit), Depends(require_csrf)],
    summary="Add a product to the wishlist (idempotent)",
    responses={**_WRITE_RESPONSES, 404: {"description": "Unknown or non-public product."}},
)
async def add_wishlist_item(
    product_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: ProductStore = Depends(product_store),
) -> Response:
    try:
        await add_to_wishlist(
            SqlWishlistRepository(session),
            products,
            SqlWishlistCounter(session),
            user_id=user.id,
            product_id=product_id,
        )
    except WishlistProductUnavailableError as exc:
        raise not_found_error() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(_wishlist_rate_limit), Depends(require_csrf)],
    summary="Remove a product from the wishlist (idempotent)",
    responses=_WRITE_RESPONSES,
)
async def remove_wishlist_item(
    product_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """No 404 on a missing entry: removing something already absent is the
    same success a client asked for, by `DELETE`'s own idempotent contract."""
    await remove_from_wishlist(
        SqlWishlistRepository(session),
        SqlWishlistCounter(session),
        user_id=user.id,
        product_id=product_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
