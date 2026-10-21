"""`GET /api/v1/admin/stl-deliveries` (VS-023b): every STL line still owed to a customer,
oldest first, keyset-paged. Admin, MFA; customers get 404 from the boundary."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.fulfillment.domain import limits
from app.identity.public import AdminBoundaryRoute
from app.ordering.public import StlDeliveryRow, stl_delivery_page

admin_router = APIRouter(prefix="/stl-deliveries", tags=["admin"], route_class=AdminBoundaryRoute)

_SEPARATOR = "|"


class StlDeliveryRead(BaseModel):
    item_id: UUID
    order_id: UUID
    order_number: str
    product_id: UUID
    product_name: str
    customer_id: UUID
    customer_email: str
    line_total_cents: int
    currency: str
    queued_at: datetime

    @classmethod
    def of(cls, row: StlDeliveryRow) -> "StlDeliveryRead":
        return cls(**vars(row))


class StlDeliveryPage(BaseModel):
    items: list[StlDeliveryRead]
    next_cursor: str | None


def encode_cursor(queued_at: datetime, item_id: UUID) -> str:
    raw = f"{queued_at.isoformat()}{_SEPARATOR}{item_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    """Exactly the `(created_at, id)` encoded; anything else is a 422 on `cursor`."""
    if raw is None:
        return None
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        moment, row_id = text.split(_SEPARATOR)
        parsed = datetime.fromisoformat(moment), UUID(row_id)
        if parsed[0].tzinfo is None:
            raise ValueError("a cursor's time is always aware")
        parsed[0].astimezone(UTC)
    except (ValueError, binascii.Error, UnicodeDecodeError, OverflowError) as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "not a valid cursor", "type": "value_error"}]
        ) from exc
    return parsed


@admin_router.get(
    "",
    response_model=StlDeliveryPage,
    summary="STL delivery queue, oldest first",
    responses={
        401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
        404: {"description": "NOT_FOUND: customers always get this."},
        422: {"description": "VALIDATION_ERROR: a bad filter or cursor."},
    },
)
async def list_stl_deliveries(
    session: AsyncSession = Depends(get_session),
    product_id: UUID | None = None,
    customer_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=limits.QUEUE_PAGE_MAX)] = limits.QUEUE_PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> StlDeliveryPage:
    rows = await stl_delivery_page(
        session,
        after=decode_cursor(cursor),
        limit=limit + 1,
        product_id=product_id,
        user_id=customer_id,
    )
    page = rows[:limit]
    more = len(rows) > limit
    return StlDeliveryPage(
        items=[StlDeliveryRead.of(row) for row in page],
        next_cursor=encode_cursor(page[-1].queued_at, page[-1].item_id) if more else None,
    )
