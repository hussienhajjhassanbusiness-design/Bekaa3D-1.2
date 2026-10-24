"""`POST /api/v1/me/orders/{order_id}/cancel` (VS-031; F-033, FR-09). The use case is
Fulfillment's, shared with the administrator's cancel; the answer is the `OrderDetail`."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.api.text import MultilineStr
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.fulfillment.public import cancel_order_by_customer
from app.identity.public import User, current_verified_user, not_found_error, require_csrf
from app.ordering.api.order_schemas import OrderDetailRead
from app.ordering.api.orders import order_detail_read
from app.ordering.domain.exceptions import LineNotFoundError, OrderNotCancellableError
from app.payments.public import OrderTotalMismatchError, RefundExceedsAvailableError

router = APIRouter(prefix="/me/orders", tags=["orders"])

CANCEL_RATE_LIMIT = 10
CANCEL_RATE_WINDOW_SECONDS = 3600
REASON_MAX = 500

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
    403: {"description": "CSRF_INVALID, or EMAIL_VERIFICATION_REQUIRED."},
    404: {"description": "NOT_FOUND: no such order, or not yours."},
    409: {
        "description": "ORDER_NOT_CANCELLABLE: `can_cancel` is false now (printing started, "
        "an unpaid online or STL-only order, or nothing left to cancel). Nothing changed."
    },
    422: {"description": "VALIDATION_ERROR."},
    429: {"description": "RATE_LIMITED: too many cancellations this hour."},
}


class CustomerOrderCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[MultilineStr | None, Field(max_length=REASON_MAX)] = None


async def _rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user; after `current_verified_user`, so an unverified caller spends no budget."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="order_cancel",
        subject=str(user.id),
        limit=CANCEL_RATE_LIMIT,
        window_seconds=CANCEL_RATE_WINDOW_SECONDS,
    )


def _not_cancellable() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="ORDER_NOT_CANCELLABLE",
        title="Order cannot be cancelled",
        detail="This order can no longer be cancelled. Nothing changed.",
    )


@router.post(
    "/{order_id}/cancel",
    response_model=OrderDetailRead,
    dependencies=[Depends(require_csrf), Depends(_rate_limit)],
    summary="Cancel your order's physical items before printing starts",
    responses=_RESPONSES,
)
async def cancel_my_order(
    order_id: UUID,
    request: Request,
    body: CustomerOrderCancelRequest | None = None,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailRead:
    """Every live physical line, all still `pending`, or nothing (FR-09); a paid order's
    refund is each line's whole remaining balance, pending until settled (ADR-043)."""
    ip = client_ip(request)
    try:
        await cancel_order_by_customer(
            session,
            order_id=order_id,
            user_id=user.id,
            at=datetime.now(UTC),
            note=((body.reason if body else None) or "").strip() or None,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except LineNotFoundError as exc:
        raise not_found_error() from exc
    except (OrderNotCancellableError, OrderTotalMismatchError, RefundExceedsAvailableError) as exc:
        raise _not_cancellable() from exc
    return await order_detail_read(session, user_id=user.id, order_id=order_id)
