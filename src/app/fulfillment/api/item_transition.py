"""`POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` (VS-023b): STL lines
only, `awaiting_delivery -> delivered`. VS-029 adds the physical edges and replaces the
provisional `OrderItemTransitionRead` with `AdminOrderDetail`."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.fulfillment.application.mark_stl_delivered import mark_stl_delivered
from app.fulfillment.domain import limits
from app.fulfillment.infrastructure.delivery_side import SqlDeliveryNotices, SqlDeliveryOrders
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.ordering.public import InvalidLineTransitionError, LineNotFoundError
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/orders", tags=["admin"], route_class=AdminBoundaryRoute)


class OrderItemTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: Literal["delivered"]


class OrderItemTransitionRead(BaseModel):
    order_id: UUID
    item_id: UUID
    fulfillment_status: Literal["delivered"] = "delivered"
    fulfilled_at: datetime
    delivered_by: UUID
    order_status: str


async def _rate_limit(
    request: Request, response: Response, claims: AccessTokenClaims = Depends(require_admin)
) -> None:
    await enforce_rate_limit(
        request,
        response,
        key_prefix="admin_stl_delivery",
        subject=str(claims.user_id),
        limit=limits.STL_DELIVERY_RATE_LIMIT,
        window_seconds=limits.STL_DELIVERY_WINDOW_SECONDS,
    )


@admin_router.post(
    "/{order_id}/items/{item_id}/transition",
    response_model=OrderItemTransitionRead,
    dependencies=[Depends(require_csrf), Depends(_rate_limit)],
    summary="Mark an STL line delivered (the file was emailed)",
    responses={
        401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
        403: {"description": "CSRF_INVALID."},
        404: {"description": "NOT_FOUND: no such order or line (customers always get this)."},
        409: {
            "description": "INVALID_STATE_TRANSITION with `reason`: `already_delivered` "
            "(with `fulfilled_at`), `line_closed`, `not_awaiting_delivery` or `not_an_stl_line`."
        },
        422: {"description": "VALIDATION_ERROR."},
        429: {"description": "RATE_LIMITED: the per-administrator hourly limit."},
    },
)
async def transition_item(
    order_id: UUID,
    item_id: UUID,
    body: OrderItemTransitionRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OrderItemTransitionRead:
    ip = client_ip(request)
    try:
        done = await mark_stl_delivered(
            SqlDeliveryOrders(session),
            SqlAuditWriter(session),
            SqlDeliveryNotices(session),
            order_id=order_id,
            item_id=item_id,
            admin_id=claims.user_id,
            at=datetime.now(UTC),
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except LineNotFoundError as exc:
        raise not_found_error() from exc
    except InvalidLineTransitionError as exc:
        extensions: dict[str, Any] = {"reason": exc.reason}
        if exc.fulfilled_at is not None:
            extensions["fulfilled_at"] = exc.fulfilled_at.isoformat()
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Line cannot make this transition",
            detail="This line cannot be marked delivered now.",
            extensions=extensions,
        ) from exc
    return OrderItemTransitionRead(
        order_id=done.order_id,
        item_id=done.item_id,
        fulfilled_at=done.fulfilled_at,
        delivered_by=done.delivered_by,
        order_status=done.order_status.value,
    )
