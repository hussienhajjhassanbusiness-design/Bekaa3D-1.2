"""`POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` (VS-023b STL, VS-029
physical): one line, one edge; the answer is the whole `AdminOrderDetail`."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.text import MultilineStr
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.fulfillment.api.admin_order_schemas import AdminOrderDetail
from app.fulfillment.api.admin_orders import audit_context, cancel_refusal, order_detail
from app.fulfillment.application.transition_line import transition_line
from app.fulfillment.domain import limits
from app.fulfillment.infrastructure.delivery_side import (
    SqlDeliveryNotices,
    SqlDeliveryOrders,
    SqlOrderPayments,
)
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.ordering.public import (
    CancelReason,
    InvalidLineTransitionError,
    LineNotFoundError,
    OrderItemStatus,
)
from app.payments.public import OrderTotalMismatchError, RefundExceedsAvailableError
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/orders", tags=["admin"], route_class=AdminBoundaryRoute)


class OrderItemTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: OrderItemStatus
    reason: Annotated[
        MultilineStr | None,
        Field(max_length=limits.NOTE_MAX, description="A note kept in the status history."),
    ] = None
    cancel_reason: CancelReason | None = Field(
        default=None,
        description="Required for `-> cancelled` from `ready_to_ship`, `returned`, "
        "`ready_for_pickup` or `shipped`; `no_show` from `ready_for_pickup` only (VS-031).",
    )


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
    response_model=AdminOrderDetail,
    dependencies=[Depends(require_csrf), Depends(_rate_limit)],
    summary="Move one line along its state machine (STL sent, or a physical step)",
    responses={
        401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
        403: {"description": "CSRF_INVALID."},
        404: {"description": "NOT_FOUND: no such order or line (customers always get this)."},
        409: {
            "description": "INVALID_STATE_TRANSITION with `reason` and the line's "
            "`fulfillment_status`: `payment_required` (an unpaid online order, BR-148), "
            "`cash_handover_required`, `not_a_legal_edge`, `line_closed`, "
            "`cancel_reason_required`, `cancel_reason_not_allowed`, `refund_exceeds_available`, "
            "or for an STL line `already_delivered` (with `fulfilled_at`) and "
            "`not_awaiting_delivery`; or ORDER_TOTAL_MISMATCH."
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
) -> AdminOrderDetail:
    request_id, ip_hash = audit_context(request)
    try:
        await transition_line(
            SqlDeliveryOrders(session),
            SqlOrderPayments(session),
            SqlAuditWriter(session),
            SqlDeliveryNotices(session),
            order_id=order_id,
            item_id=item_id,
            target=body.target_status,
            admin_id=claims.user_id,
            at=datetime.now(UTC),
            note=(body.reason or "").strip() or None,
            request_id=request_id,
            ip_hash=ip_hash,
            cancel_reason=body.cancel_reason,
        )
    except LineNotFoundError as exc:
        raise not_found_error() from exc
    except (OrderTotalMismatchError, RefundExceedsAvailableError) as exc:
        raise await cancel_refusal(exc, order_id) from exc
    except InvalidLineTransitionError as exc:
        extensions: dict[str, Any] = {"reason": exc.reason}
        if exc.fulfilled_at is not None:
            extensions["fulfilled_at"] = exc.fulfilled_at.isoformat()
        if exc.current_status is not None:
            extensions["fulfillment_status"] = exc.current_status
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Line cannot make this transition",
            detail="This line cannot make that transition now.",
            extensions=extensions,
        ) from exc
    return await order_detail(session, order_id)
