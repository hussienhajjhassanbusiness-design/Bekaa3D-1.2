"""`GET/PATCH /api/v1/admin/orders[/{id}]` and `POST …/{id}/cash-handover` (VS-029; F-060,
F-062, F-054). Admin, MFA; customers get 404 from the boundary (ADR-017)."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.fulfillment.api.admin_order_schemas import (
    AdminOrderDetail,
    AdminOrderPage,
    AdminOrderSummaryRead,
    AdminOrderUpdate,
    CashHandoverRequest,
)
from app.fulfillment.api.stl_deliveries import decode_cursor, encode_cursor
from app.fulfillment.application.admin_order_detail import admin_order_detail
from app.fulfillment.application.record_cash_handover import record_cash_handover
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
    AdminOrderFilters,
    CashAmountMismatchError,
    FulfillmentMethod,
    HandoverRefusedError,
    LineNotFoundError,
    OrderStatus,
    PaymentMethod,
    admin_order_page,
    admin_orders,
)
from app.payments.public import CashAlreadyRecordedError
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/orders", tags=["admin"], route_class=AdminBoundaryRoute)

_COMMON: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
    404: {"description": "NOT_FOUND: no such order (customers always get this)."},
}


def _limit(prefix: str, limit: int) -> Any:
    async def dependency(
        request: Request, response: Response, claims: AccessTokenClaims = Depends(require_admin)
    ) -> None:
        await enforce_rate_limit(
            request,
            response,
            key_prefix=prefix,
            subject=str(claims.user_id),
            limit=limit,
            window_seconds=limits.RATE_WINDOW_SECONDS,
        )

    return dependency


def audit_context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


async def order_detail(session: AsyncSession, order_id: UUID) -> AdminOrderDetail:
    """The detail every admin order route answers with, read in the route's transaction."""
    view = await admin_order_detail(admin_orders(session), SqlOrderPayments(session), order_id)
    if view is None:
        raise not_found_error()
    return AdminOrderDetail.of(view, get_settings().media_public_url)


def _utc(value: datetime | None, field: str) -> datetime | None:
    try:
        return value.astimezone(UTC) if value is not None else None
    except OverflowError as exc:
        raise RequestValidationError(
            [{"loc": ("query", field), "msg": "out of range", "type": "value_error"}]
        ) from exc


@admin_router.get(
    "",
    response_model=AdminOrderPage,
    summary="Fulfillment queue, newest first; never an unpaid online order",
    responses={**_COMMON, 422: {"description": "VALIDATION_ERROR: a bad filter or cursor."}},
)
async def list_orders(
    session: AsyncSession = Depends(get_session),
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    fulfillment_method: FulfillmentMethod | None = None,
    payment_method: PaymentMethod | None = None,
    payment_due: Annotated[
        bool | None, Query(description="true: the 'cash due' view (unpaid cash orders).")
    ] = None,
    customer_id: UUID | None = None,
    order_number: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    placed_after: Annotated[AwareDatetime | None, Query(description="Inclusive.")] = None,
    placed_before: Annotated[AwareDatetime | None, Query(description="Exclusive.")] = None,
    limit: Annotated[int, Query(ge=1, le=limits.QUEUE_PAGE_MAX)] = limits.QUEUE_PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> AdminOrderPage:
    if status_filter is OrderStatus.PENDING_PAYMENT:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "status"),
                    "msg": "unpaid online orders are never in the queue",
                    "type": "value_error",
                }
            ]
        )
    filters = AdminOrderFilters(
        status=status_filter,
        fulfillment_method=fulfillment_method,
        payment_method=payment_method,
        payment_due=payment_due,
        customer_id=customer_id,
        order_number=order_number,
        placed_after=_utc(placed_after, "placed_after"),
        placed_before=_utc(placed_before, "placed_before"),
    )
    rows = await admin_order_page(session, filters, after=decode_cursor(cursor), limit=limit + 1)
    page = rows[:limit]
    more = len(rows) > limit
    return AdminOrderPage(
        items=[AdminOrderSummaryRead.of(row) for row in page],
        next_cursor=encode_cursor(page[-1].placed_at, page[-1].id) if more else None,
    )


@admin_router.get(
    "/{order_id}",
    response_model=AdminOrderDetail,
    summary="One order with its lines' available actions, payments and full history",
    responses=_COMMON,
)
async def get_order(
    order_id: UUID, session: AsyncSession = Depends(get_session)
) -> AdminOrderDetail:
    return await order_detail(session, order_id)


@admin_router.patch(
    "/{order_id}",
    response_model=AdminOrderDetail,
    dependencies=[
        Depends(require_csrf),
        Depends(_limit("admin_order_note", limits.ADMIN_NOTE_RATE_LIMIT)),
    ],
    summary="Set the internal admin note (the only editable field)",
    responses={
        **_COMMON,
        403: {"description": "CSRF_INVALID."},
        422: {"description": "VALIDATION_ERROR."},
        429: {"description": "RATE_LIMITED."},
    },
)
async def update_order(
    order_id: UUID,
    body: AdminOrderUpdate,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminOrderDetail:
    note = body.note()
    if not await admin_orders(session).set_admin_note(order_id, note, at=datetime.now(UTC)):
        raise not_found_error()
    request_id, ip_hash = audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="order.admin_note_updated",
        entity_type="order",
        entity_id=order_id,
        after_data={"has_note": note is not None},
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return await order_detail(session, order_id)


@admin_router.post(
    "/{order_id}/cash-handover",
    response_model=AdminOrderDetail,
    dependencies=[
        Depends(require_csrf),
        Depends(_limit("admin_cash_handover", limits.HANDOVER_RATE_LIMIT)),
    ],
    summary="Record the cash collected and mark every live line delivered / picked up",
    responses={
        **_COMMON,
        403: {"description": "CSRF_INVALID."},
        409: {
            "description": "INVALID_STATE_TRANSITION with `reason`: `not_a_cash_order`, "
            "`no_live_line`, `already_recorded` or `lines_not_ready`."
        },
        422: {
            "description": "CASH_AMOUNT_MISMATCH (with `amount_due`): not exactly the live "
            "total above zero; or VALIDATION_ERROR."
        },
        429: {"description": "RATE_LIMITED."},
    },
)
async def cash_handover(
    order_id: UUID,
    body: CashHandoverRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminOrderDetail:
    request_id, ip_hash = audit_context(request)
    note = (body.note or "").strip() or None
    try:
        await record_cash_handover(
            SqlDeliveryOrders(session),
            SqlOrderPayments(session),
            SqlAuditWriter(session),
            SqlDeliveryNotices(session),
            order_id=order_id,
            amount_cents=body.amount_cents,
            admin_id=claims.user_id,
            at=datetime.now(UTC),
            note=note,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except LineNotFoundError as exc:
        raise not_found_error() from exc
    except (HandoverRefusedError, CashAlreadyRecordedError) as exc:
        reason = exc.reason if isinstance(exc, HandoverRefusedError) else "already_recorded"
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Cash handover refused",
            detail="This order cannot take a cash handover now.",
            extensions={"reason": reason},
        ) from exc
    except CashAmountMismatchError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CASH_AMOUNT_MISMATCH",
            title="Cash amount does not match",
            detail="The cash entered must equal the amount due.",
            extensions={"amount_due": {"amount_cents": exc.due_cents, "currency": "USD"}},
        ) from exc
    return await order_detail(session, order_id)
