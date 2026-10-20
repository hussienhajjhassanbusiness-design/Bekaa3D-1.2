"""`POST /api/v1/admin/orders/{order_id}/release` (VS-024 plan 2.5): the manual exit for
an unpaid order the job cannot release. After the 24 h grace, with a reason, and with
`events_reviewed` when unprocessed events exist. The provider is never called."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.api.text import MultilineStr
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.payments.public import (
    ManualReleaseRefusedError,
    OrderNotFoundError,
    limits,
    release_order_by_admin,
)
from app.platform.public import settings_reader

admin_router = APIRouter(prefix="/orders", tags=["admin"], route_class=AdminBoundaryRoute)

HOLD_SETTING = "checkout_hold_period"


class OrderReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[
        MultilineStr, Field(min_length=limits.REASON_MIN, max_length=limits.REASON_MAX)
    ]
    events_reviewed: bool = False


class OrderReleaseRead(BaseModel):
    order_id: UUID
    status: Literal["cancelled"] = "cancelled"
    cancelled_at: datetime
    attempts_expired: list[UUID]
    events_dismissed: list[UUID]


async def _release_rate_limit(
    request: Request, response: Response, claims: AccessTokenClaims = Depends(require_admin)
) -> None:
    await enforce_rate_limit(
        request,
        response,
        key_prefix="admin_order_release",
        subject=str(claims.user_id),
        limit=limits.RELEASE_RATE_LIMIT,
        window_seconds=limits.ADMIN_ACTION_WINDOW_SECONDS,
    )


_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
    403: {"description": "CSRF_INVALID."},
    404: {"description": "NOT_FOUND: no such order (customers always get this)."},
    409: {
        "description": "INVALID_STATE_TRANSITION with `reason`: `cash_order`, "
        "`order_cancelled`, `order_not_payable`, `grace_not_elapsed` (with "
        "`release_available_at`) or `unprocessed_events` (with `count`)."
    },
    422: {"description": "VALIDATION_ERROR (a missing or short `reason`)."},
    429: {"description": "RATE_LIMITED: this action's per-administrator hourly limit."},
}


@admin_router.post(
    "/{order_id}/release",
    response_model=OrderReleaseRead,
    dependencies=[Depends(require_csrf), Depends(_release_rate_limit)],
    summary="Release an unpaid order's hold by hand",
    responses=_RESPONSES,
)
async def release_order(
    order_id: UUID,
    body: OrderReleaseRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OrderReleaseRead:
    hold = await settings_reader(session).get_duration_seconds(HOLD_SETTING)
    ip = client_ip(request)
    try:
        released = await release_order_by_admin(
            session,
            order_id,
            admin_id=claims.user_id,
            reason=body.reason,
            events_reviewed=body.events_reviewed,
            hold=timedelta(seconds=hold),
            now=datetime.now(UTC),
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(ip) if ip else None,
        )
    except OrderNotFoundError as exc:
        raise not_found_error() from exc
    except ManualReleaseRefusedError as exc:
        extensions: dict[str, Any] = {"reason": exc.reason}
        if exc.reason == "grace_not_elapsed":
            extensions["release_available_at"] = exc.available_at.isoformat()
        if exc.reason == "unprocessed_events":
            extensions["count"] = exc.unprocessed_events
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Order cannot be released",
            detail="This order cannot be released now.",
            extensions=extensions,
        ) from exc
    return OrderReleaseRead(
        order_id=released.order_id,
        cancelled_at=released.cancelled_at,
        attempts_expired=list(released.attempts_expired),
        events_dismissed=list(released.events_dismissed),
    )
