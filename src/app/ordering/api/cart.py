"""The customer's cart (VS-022, FR-05, api-endpoints.md 10.1). Reading needs a session;
writes need a verified email, CSRF and one shared per-user rate limit."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.application.ports import CartProductReader
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.identity.public import (
    User,
    current_user,
    current_verified_user,
    not_found_error,
    require_csrf,
)
from app.ordering.api.cart_schemas import CartItemAdd, CartItemQuantityUpdate, CartRead
from app.ordering.api.problems import already_owned_error
from app.ordering.application.services.cart import (
    add_item,
    read_cart,
    remove_item,
    set_item_quantity,
)
from app.ordering.domain.exceptions import (
    CartLineLimitReachedError,
    CartLineNotFoundError,
    ProductAlreadyOwnedError,
    ProductNotPurchasableError,
    QuantityExceedsLimitError,
)
from app.ordering.infrastructure.carts import SqlCartStore
from app.ordering.infrastructure.orders import SqlOrderStore

router = APIRouter(prefix="/cart", tags=["cart"])

_RATE_LIMIT = 300
_RATE_WINDOW_SECONDS = 3600

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_READ_RESPONSES,
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    429: {"description": "RATE_LIMITED: too many cart changes this hour."},
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"description": "PRODUCT_ALREADY_OWNED: the caller already owns this STL (VS-023)."}
}
_UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {
        "description": "PRODUCT_NOT_PURCHASABLE (with `reason`), QUANTITY_EXCEEDS_LIMIT "
        "(with `max_quantity`), CART_LINE_LIMIT_REACHED (with `limit`), or VALIDATION_ERROR."
    }
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "The caller's cart has no line for this product."}
}


async def _cart_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user, not per IP. Depends on `current_verified_user`, so an anonymous or
    unverified caller never consumes the budget (as `_wishlist_rate_limit` does)."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="cart",
        subject=str(user.id),
        limit=_RATE_LIMIT,
        window_seconds=_RATE_WINDOW_SECONDS,
    )


def _translate(exc: Exception) -> ApiError:
    if isinstance(exc, ProductNotPurchasableError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="PRODUCT_NOT_PURCHASABLE",
            title="Product cannot be bought online",
            detail="This product cannot be added to the cart right now.",
            extensions={"reason": str(exc.reason)},
        )
    if isinstance(exc, QuantityExceedsLimitError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="QUANTITY_EXCEEDS_LIMIT",
            title="Quantity exceeds the limit",
            detail=f"At most {exc.max_quantity} of this product fit in one cart line.",
            extensions={
                "max_quantity": exc.max_quantity,
                "requested": exc.requested,
                "current_quantity": exc.current_quantity,
            },
        )
    if isinstance(exc, ProductAlreadyOwnedError):
        return already_owned_error(exc.product_ids)
    if isinstance(exc, CartLineLimitReachedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CART_LINE_LIMIT_REACHED",
            title="Cart is full",
            detail=f"A cart holds at most {exc.limit} different products.",
            extensions={"limit": exc.limit},
        )
    return not_found_error()


_DOMAIN_ERRORS = (
    ProductAlreadyOwnedError,
    ProductNotPurchasableError,
    QuantityExceedsLimitError,
    CartLineLimitReachedError,
    CartLineNotFoundError,
)


async def _read(session: AsyncSession, products: CartProductReader, user: User) -> CartRead:
    view = await read_cart(SqlCartStore(session), products, user_id=user.id)
    return CartRead.of(view, get_settings().media_public_url)


@router.get(
    "",
    response_model=CartRead,
    summary="Read the authenticated user's own cart",
    responses=_READ_RESPONSES,
)
async def get_cart(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> CartRead:
    """Never creates a cart: a user who has not written one gets `id: null`."""
    return await _read(session, products, user)


@router.post(
    "/items",
    response_model=CartRead,
    dependencies=[Depends(_cart_rate_limit), Depends(require_csrf)],
    summary="Add a product to the cart; an existing line merges quantities",
    responses={**_WRITE_RESPONSES, **_CONFLICT, **_UNPROCESSABLE},
)
async def add_cart_item(
    body: CartItemAdd,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> CartRead:
    try:
        await add_item(
            SqlCartStore(session),
            products,
            user_id=user.id,
            product_id=body.product_id,
            quantity=body.quantity,
            ownership=SqlOrderStore(session),
        )
    except _DOMAIN_ERRORS as exc:
        raise _translate(exc) from exc
    return await _read(session, products, user)


@router.patch(
    "/items/{product_id}",
    response_model=CartRead,
    dependencies=[Depends(_cart_rate_limit), Depends(require_csrf)],
    summary="Set the absolute quantity of a cart line",
    responses={**_WRITE_RESPONSES, **_UNPROCESSABLE, **_NOT_FOUND},
)
async def update_cart_item(
    product_id: UUID,
    body: CartItemQuantityUpdate,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
    products: CartProductReader = Depends(cart_product_reader),
) -> CartRead:
    try:
        await set_item_quantity(
            SqlCartStore(session),
            products,
            user_id=user.id,
            product_id=product_id,
            quantity=body.quantity,
        )
    except _DOMAIN_ERRORS as exc:
        raise _translate(exc) from exc
    return await _read(session, products, user)


@router.delete(
    "/items/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(_cart_rate_limit), Depends(require_csrf)],
    summary="Remove a line from the cart",
    responses={**_WRITE_RESPONSES, **_NOT_FOUND},
)
async def delete_cart_item(
    product_id: UUID,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """404 when the line is absent (api-endpoints.md 10.1), unlike the wishlist."""
    try:
        await remove_item(SqlCartStore(session), user_id=user.id, product_id=product_id)
    except CartLineNotFoundError as exc:
        raise not_found_error() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
