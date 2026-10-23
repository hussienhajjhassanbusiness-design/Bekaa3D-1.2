"""`/api/v1/admin/cash-blocks` (VS-029; SRS 9.8.6, ADR-024 d6): list, search by phone and
clear cash payment blocks. The phone travels in a body only and is hashed before matching."""

from datetime import UTC, datetime
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.api.text import PlainStr
from app.core.phone import InvalidPhoneNumberError, normalise_lebanese_phone
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip, hash_phone
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
    require_csrf,
)
from app.ordering.api.orders import _decode_cursor, _encode_cursor
from app.ordering.domain.admin_orders import CashBlock
from app.ordering.domain.enums import CancelReason
from app.ordering.infrastructure.cash import SqlCashBlockStore
from app.platform.public import SqlAuditWriter

admin_router = APIRouter(prefix="/cash-blocks", tags=["admin"], route_class=AdminBoundaryRoute)

PAGE_DEFAULT = 25
PAGE_MAX = 100
RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 3600
_COMMON: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
    404: {"description": "NOT_FOUND: customers always get this."},
}


class CashPaymentBlockRead(BaseModel):
    """Never the phone or its hash (ADR-038)."""

    id: UUID
    customer_id: UUID
    order_id: UUID
    order_number: str
    reason: CancelReason
    created_at: datetime
    active: bool
    cleared_at: datetime | None
    cleared_by: UUID | None

    @classmethod
    def of(cls, b: CashBlock) -> Self:
        return cls(
            id=b.id,
            customer_id=b.user_id,
            order_id=b.order_id,
            order_number=b.order_number,
            reason=b.reason,
            created_at=b.created_at,
            active=b.cleared_at is None,
            cleared_at=b.cleared_at,
            cleared_by=b.cleared_by,
        )


class CashPaymentBlockPage(BaseModel):
    items: list[CashPaymentBlockRead]
    next_cursor: str | None


class CashBlockSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: Annotated[PlainStr, Field(max_length=32)]
    active: bool | None = None
    limit: Annotated[int, Field(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT
    cursor: Annotated[PlainStr | None, Field(max_length=200)] = None

    @field_validator("phone")
    @classmethod
    def _normalise(cls, value: str) -> str:
        """Any spelling of one number matches the same blocks (VS-028 plan D10)."""
        try:
            return normalise_lebanese_phone(value)
        except InvalidPhoneNumberError:
            raise ValueError("Enter a valid Lebanese phone number.") from None


async def _rate_limit(
    request: Request, response: Response, claims: AccessTokenClaims = Depends(require_admin)
) -> None:
    await enforce_rate_limit(
        request,
        response,
        key_prefix="admin_cash_blocks",
        subject=str(claims.user_id),
        limit=RATE_LIMIT,
        window_seconds=RATE_WINDOW_SECONDS,
    )


async def _page(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    active: bool | None,
    phone_hash: str | None,
    cursor: str | None,
    limit: int,
) -> CashPaymentBlockPage:
    rows = await SqlCashBlockStore(session).page(
        user_id=user_id,
        active=active,
        phone_hash=phone_hash,
        after=_decode_cursor(cursor),
        limit=limit + 1,
    )
    page = rows[:limit]
    last = page[-1] if len(rows) > limit else None
    return CashPaymentBlockPage(
        items=[CashPaymentBlockRead.of(row) for row in page],
        next_cursor=_encode_cursor(last.created_at, last.id) if last is not None else None,
    )


@admin_router.get(
    "",
    response_model=CashPaymentBlockPage,
    summary="Cash payment blocks, newest first",
    responses={**_COMMON, 422: {"description": "VALIDATION_ERROR: a bad filter or cursor."}},
)
async def list_blocks(
    session: AsyncSession = Depends(get_session),
    customer_id: UUID | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> CashPaymentBlockPage:
    return await _page(
        session, user_id=customer_id, active=active, phone_hash=None, cursor=cursor, limit=limit
    )


@admin_router.post(
    "/search",
    response_model=CashPaymentBlockPage,
    dependencies=[Depends(require_csrf), Depends(_rate_limit)],
    summary="Find blocks by contact phone (in the body, so it never reaches request logs)",
    responses={
        **_COMMON,
        403: {"description": "CSRF_INVALID."},
        422: {"description": "VALIDATION_ERROR: not a Lebanese phone, or a bad cursor."},
        429: {"description": "RATE_LIMITED."},
    },
)
async def search_blocks(
    body: CashBlockSearchRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CashPaymentBlockPage:
    """One `cash_block.searched` audit row per search: filters, count and ids only, never
    the phone or its hash (VS-030 2.6, Q8)."""
    page = await _page(
        session,
        user_id=None,
        active=body.active,
        phone_hash=hash_phone(body.phone),
        cursor=body.cursor,
        limit=body.limit,
    )
    ip = client_ip(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="cash_block.searched",
        entity_type="cash_block",
        entity_id=None,
        after_data={
            "active": body.active,
            "limit": body.limit,
            "result_count": len(page.items),
            "block_ids": [str(item.id) for item in page.items],
        },
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(ip) if ip else None,
    )
    return page


@admin_router.post(
    "/{block_id}/clear",
    response_model=CashPaymentBlockRead,
    dependencies=[Depends(require_csrf), Depends(_rate_limit)],
    summary="Clear a block; clearing a cleared block changes nothing",
    responses={
        **_COMMON,
        403: {"description": "CSRF_INVALID."},
        429: {"description": "RATE_LIMITED."},
    },
)
async def clear_block(
    block_id: UUID,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CashPaymentBlockRead:
    store = SqlCashBlockStore(session)
    block = await store.lock(block_id)
    if block is None:
        raise not_found_error()
    if block.cleared_at is not None:
        return CashPaymentBlockRead.of(block)
    at = datetime.now(UTC)
    await store.clear(block_id, admin_id=claims.user_id, at=at)
    ip = client_ip(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="cash_block.cleared",
        entity_type="cash_payment_block",
        entity_id=block_id,
        before_data={"cleared_at": None},
        after_data={
            "cleared_at": at.isoformat(),
            "customer_id": str(block.user_id),
            "order_id": str(block.order_id),
            "reason": block.reason.value,
        },
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(ip) if ip else None,
    )
    cleared = CashBlock(**(vars(block) | {"cleared_at": at, "cleared_by": claims.user_id}))
    return CashPaymentBlockRead.of(cleared)
