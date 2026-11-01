"""`GET /api/v1/me/orders` and `GET /api/v1/me/orders/{order_id}` (VS-025, F-026, F-027).
Reads: a session is enough, no verified email and no rate limit, like `GET /cart`."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.catalog.public import PriceRead
from app.core.config import get_settings
from app.identity.public import User, current_user, not_found_error
from app.negotiation.public import SqlOfferCheckouts
from app.ordering.api.order_schemas import (
    OrderDetailRead,
    OrderPage,
    OrderRefundRead,
    OrderSummaryRead,
)
from app.ordering.application.ports import OrderFilters
from app.ordering.application.services.holds import read_holds
from app.ordering.application.services.order_history import (
    RetryContext,
    get_order,
    list_orders,
)
from app.ordering.domain.enums import OrderStatus
from app.ordering.infrastructure.order_history import SqlOrderHistory
from app.payments.public import customer_refunds, order_payment_reader
from app.platform.public import settings_reader

router = APIRouter(prefix="/me/orders", tags=["orders"])

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_CURSOR_SEPARATOR = "|"
_BAD_CURSOR = "cursor is not a valid pagination cursor"

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
}


def _encode_cursor(placed_at: datetime, order_id: UUID) -> str:
    raw = f"{placed_at.isoformat()}{_CURSOR_SEPARATOR}{order_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse_cursor(raw: str) -> tuple[datetime, UUID]:
    """Strict, as wishlist.py's: a half-valid cursor would page from the wrong place."""
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        placed_raw, separator, id_raw = decoded.partition(_CURSOR_SEPARATOR)
        placed_at, order_id = datetime.fromisoformat(placed_raw), UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(_BAD_CURSOR) from exc
    if not separator or placed_at.tzinfo is None:
        raise ValueError(_BAD_CURSOR)
    return _utc(placed_at, _BAD_CURSOR), order_id


def _utc(value: datetime, message: str) -> datetime:
    """asyncpg converts to UTC; an instant with no UTC equivalent was a 500 (BUG-36)."""
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError(message) from exc


def _invalid(field: str, exc: ValueError) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": str(exc), "type": "value_error"}]
    )


def _decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    try:
        return _parse_cursor(raw) if raw is not None else None
    except ValueError as exc:
        raise _invalid("cursor", exc) from exc


def _bound(value: datetime | None, field: str) -> datetime | None:
    try:
        return _utc(value, f"{field} is out of range") if value is not None else None
    except ValueError as exc:
        raise _invalid(field, exc) from exc


@router.get(
    "",
    response_model=OrderPage,
    summary="List the caller's own orders, newest first",
    responses=_RESPONSES,
)
async def list_my_orders(
    status: OrderStatus | None = Query(default=None),
    placed_after: AwareDatetime | None = Query(default=None, description="Inclusive."),
    placed_before: AwareDatetime | None = Query(default=None, description="Exclusive."),
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderPage:
    filters = OrderFilters(
        status=status,
        placed_after=_bound(placed_after, "placed_after"),
        placed_before=_bound(placed_before, "placed_before"),
    )
    rows = await list_orders(
        SqlOrderHistory(session),
        order_payment_reader(session),
        user_id=user.id,
        filters=filters,
        after=_decode_cursor(cursor),
        limit=limit + 1,
    )
    page = rows[:limit]
    last = page[-1].order if len(rows) > limit else None
    return OrderPage(
        items=[OrderSummaryRead.of(row) for row in page],
        next_cursor=_encode_cursor(last.placed_at, last.id) if last is not None else None,
    )


@router.get(
    "/{order_id}",
    response_model=OrderDetailRead,
    summary="One of the caller's own orders, as bought",
    responses={**_RESPONSES, 404: {"description": "No such order among the caller's own."}},
)
async def get_my_order(
    order_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailRead:
    return await order_detail_read(session, user_id=user.id, order_id=order_id)


async def order_detail_read(
    session: AsyncSession, *, user_id: UUID, order_id: UUID
) -> OrderDetailRead:
    """The owner's `OrderDetail`, also returned by VS-029b's POSTs; 404 if not theirs."""
    holds = await read_holds(settings_reader(session))
    view = await get_order(
        SqlOrderHistory(session),
        order_payment_reader(session),
        user_id=user_id,
        order_id=order_id,
        retry=RetryContext(SqlOfferCheckouts(session), holds, datetime.now(UTC)),
    )
    if view is None:
        raise not_found_error()
    read = OrderDetailRead.of(view, get_settings().media_public_url)
    refunds = [
        OrderRefundRead(
            kind=r.kind.value,
            status=r.status,
            amount=PriceRead(amount_cents=r.amount_cents, currency=r.currency),
            created_at=r.created_at,
        )
        for r in await customer_refunds(session, order_id)
    ]
    return read.model_copy(update={"refunds": refunds})
