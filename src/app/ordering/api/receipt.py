"""`POST /api/v1/me/orders/{order_id}/confirm-receipt` and `…/report-problem` (VS-029b;
F-069, FR-21). Signed-in POSTs from the order page only: the email buttons just open it."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.api.text import MultilineStr
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.engagement.public import PROBLEM_REPORT_MESSAGE_MAX
from app.identity.public import (
    User,
    current_verified_user,
    not_found_error,
    require_csrf,
    unauthenticated_error,
)
from app.ordering.api.order_schemas import OrderDetailRead
from app.ordering.api.orders import order_detail_read
from app.ordering.application.services.receipt import confirm_receipt, report_problem
from app.ordering.domain.exceptions import (
    CustomerAccountClosedError,
    NoDeliveredLineError,
    ReceiptOrderNotFoundError,
)
from app.ordering.infrastructure.checkout_addresses import SqlCustomerAccounts
from app.ordering.infrastructure.orders import SqlOrderStore
from app.ordering.infrastructure.problem_reports import EngagementProblemReportInbox
from app.platform.public import SqlAuditWriter

router = APIRouter(prefix="/me/orders", tags=["orders"])

REPORT_RATE_LIMIT = 5
REPORT_RATE_WINDOW_SECONDS = 3600

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
    403: {"description": "CSRF_INVALID, or EMAIL_VERIFICATION_REQUIRED."},
    404: {"description": "NOT_FOUND: no such order, or not yours."},
    409: {
        "description": "INVALID_STATE_TRANSITION (`reason`: `no_delivered_line`): no physical "
        "line is delivered or picked up."
    },
}


class ProblemReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: MultilineStr = Field(max_length=PROBLEM_REPORT_MESSAGE_MAX)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


async def _report_rate_limit(
    request: Request, response: Response, user: User = Depends(current_verified_user)
) -> None:
    """Per user; after `current_verified_user`, so an unverified caller spends no budget."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="problem_report",
        subject=str(user.id),
        limit=REPORT_RATE_LIMIT,
        window_seconds=REPORT_RATE_WINDOW_SECONDS,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


def _no_delivered_line() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Nothing has been received yet",
        detail="No item of this order has been delivered or picked up.",
        extensions={"reason": NoDeliveredLineError.reason},
    )


@router.post(
    "/{order_id}/confirm-receipt",
    response_model=OrderDetailRead,
    dependencies=[Depends(require_csrf)],
    summary='Say "I got it" for the delivered or picked-up items of your order',
    responses=_RESPONSES,
)
async def confirm_my_receipt(
    order_id: UUID,
    request: Request,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailRead:
    request_id, ip_hash = _context(request)
    try:
        await confirm_receipt(
            SqlOrderStore(session),
            SqlAuditWriter(session),
            user_id=user.id,
            order_id=order_id,
            clock=_now,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReceiptOrderNotFoundError as exc:
        raise not_found_error() from exc
    except NoDeliveredLineError as exc:
        raise _no_delivered_line() from exc
    return await order_detail_read(session, user_id=user.id, order_id=order_id)


@router.post(
    "/{order_id}/report-problem",
    status_code=status.HTTP_201_CREATED,
    response_model=OrderDetailRead,
    # CSRF first, so a forged cross-site POST spends none of the customer's five.
    dependencies=[Depends(require_csrf), Depends(_report_rate_limit)],
    summary="Report a problem with the delivered or picked-up items of your order",
    responses={
        **_RESPONSES,
        422: {"description": "VALIDATION_ERROR: a blank or over-long message."},
        429: {"description": "RATE_LIMITED: too many problem reports this hour."},
    },
)
async def report_my_problem(
    order_id: UUID,
    body: ProblemReportCreate,
    request: Request,
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailRead:
    """The message body is never logged or audited; it lives in the contact queue only."""
    request_id, ip_hash = _context(request)
    try:
        await report_problem(
            SqlOrderStore(session),
            EngagementProblemReportInbox(session),
            SqlCustomerAccounts(session),
            SqlAuditWriter(session),
            user_id=user.id,
            email=user.email,
            order_id=order_id,
            message=body.message,
            clock=_now,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except ReceiptOrderNotFoundError as exc:
        raise not_found_error() from exc
    except NoDeliveredLineError as exc:
        raise _no_delivered_line() from exc
    except CustomerAccountClosedError as exc:
        raise unauthenticated_error() from exc
    return await order_detail_read(session, user_id=user.id, order_id=order_id)
