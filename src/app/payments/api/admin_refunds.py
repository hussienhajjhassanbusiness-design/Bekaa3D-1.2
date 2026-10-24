"""Admin refunds (VS-030 plan 2.1-2.4): create, list, get, settle, fail, reissue and void.
Mounted on the admin router (admin, MFA); every write needs CSRF and a per-admin limit.
No provider is ever called (ADR-024 d16): the admin pays in the dashboard, then settles."""

import base64
import binascii
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Self
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, get_session
from app.api.text import MultilineStr, PlainStr
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
from app.payments.application.services.refunds import (
    AuditContext,
    create_refund,
    fail_refund,
    reissue_refund,
    settle_refund,
    void_refund,
)
from app.payments.domain import limits
from app.payments.domain.alerts import AlertKind, repeat_window
from app.payments.domain.enums import PaymentProvider, RefundKind, RefundStatus
from app.payments.domain.exceptions import (
    OrderNotPaidError,
    OrderTotalMismatchError,
    RefundExceedsAvailableError,
    RefundNotFoundError,
    RefundRefusedError,
    RefundRequiresCancellationError,
)
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.alerts import SqlPaymentAlerts
from app.payments.infrastructure.refund_side import refund_deps
from app.payments.infrastructure.refunds import RefundFilters, RefundRow, refund_page, refund_row
from app.platform.public import (
    IDEMPOTENCY_TTL,
    Conflict,
    InProgress,
    Replay,
    idempotency_store,
    request_hash,
)

logger = structlog.get_logger()

admin_router = APIRouter(tags=["admin"], route_class=AdminBoundaryRoute)

# Same shape as checkout's key (`ordering.api.checkout_schemas`).
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._:-]{8,255}$"
REPLAYED = {"Idempotent-Replayed": "true"}
CREATE_SCOPE = "admin_refund_create"
REISSUE_SCOPE = "admin_refund_reissue"
_SEPARATOR = "|"

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description="8-255 characters of [A-Za-z0-9._:-]; one key per intended refund.",
    ),
]

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
    404: {"description": "NOT_FOUND: no such refund or order (customers always get this)."},
    429: {"description": "RATE_LIMITED: this action's per-administrator hourly limit."},
}
_WRITE = {**_RESPONSES, 403: {"description": "CSRF_INVALID."}}
_TRANSITION = {
    **_WRITE,
    409: {
        "description": "INVALID_STATE_TRANSITION (`reason`: `not_pending`, `not_failed`, "
        "`already_settled`, `already_reissued` with `reissued_by_refund_id`, "
        "`line_already_refunded`, `line_already_cancelled`), or ORDER_TOTAL_MISMATCH "
        "(never on settle)."
    },
    422: {"description": "VALIDATION_ERROR."},
}

_REFERENCE_MAX = limits.SETTLEMENT_REFERENCE_MAX
Reason = Annotated[MultilineStr, Field(min_length=1, max_length=limits.REFUND_TEXT_MAX)]


class RefundItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_item_id: UUID
    amount_cents: Annotated[int, Field(gt=0, le=limits.REFUND_MAX_AMOUNT_CENTS)]


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[
        list[RefundItemCreate], Field(min_length=1, max_length=limits.REFUND_MAX_ITEMS)
    ]
    reason: Reason

    @field_validator("items")
    @classmethod
    def _unique(cls, items: list[RefundItemCreate]) -> list[RefundItemCreate]:
        if len({item.order_item_id for item in items}) != len(items):
            raise ValueError("each order_item_id may appear once")
        return items


class RefundSettlementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: Annotated[PlainStr, Field(max_length=_REFERENCE_MAX)] | None = None
    note: Annotated[MultilineStr, Field(max_length=limits.REFUND_TEXT_MAX)] | None = None


class RefundFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class RefundVoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class RefundItemRead(BaseModel):
    order_item_id: UUID
    product_name: str
    amount_cents: int


class RefundDetail(BaseModel):
    """Never a phone, hash, address or provider reference (plan 2.2)."""

    id: UUID
    order_id: UUID
    order_number: str
    customer_id: UUID
    payment_id: UUID
    payment_provider: PaymentProvider
    kind: RefundKind
    status: RefundStatus
    owed: bool = Field(description="Failed and not reissued: still in the obligations queue.")
    amount_cents: int
    currency: str
    reason: str
    requested_by: UUID | None
    approved_by: UUID | None
    items: list[RefundItemRead]
    reissue_of_refund_id: UUID | None
    reissued_by_refund_id: UUID | None
    reissued_at: datetime | None
    settled_at: datetime | None
    settled_by: UUID | None
    settlement_reference: str | None
    settlement_note: str | None
    failed_at: datetime | None
    failed_by: UUID | None
    failure_reason: str | None
    voided_at: datetime | None
    voided_by: UUID | None
    void_reason: str | None
    created_at: datetime

    @classmethod
    def of(cls, row: RefundRow) -> Self:
        fields = {k: v for k, v in vars(row).items() if k != "items"}
        owed = row.status is RefundStatus.FAILED and row.reissued_at is None
        items = [RefundItemRead(**vars(item)) for item in row.items]
        return cls(**fields, owed=owed, items=items)


class RefundPage(BaseModel):
    items: list[RefundDetail]
    next_cursor: str | None = Field(description="Opaque; pass back as `cursor`. Null at the end.")


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
            window_seconds=limits.ADMIN_ACTION_WINDOW_SECONDS,
        )

    return dependency


_WRITE_LIMIT = Depends(_limit("admin_refund_write", limits.REFUND_WRITE_RATE_LIMIT))
_READ_LIMIT = Depends(_limit("admin_refund_read", limits.REFUND_READ_RATE_LIMIT))


def _ctx(request: Request, claims: AccessTokenClaims) -> AuditContext:
    ip = client_ip(request)
    return AuditContext(
        claims.user_id, getattr(request.state, "request_id", None), hash_ip(ip) if ip else None
    )


def _invalid(reason: str, **extra: Any) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Not allowed for this refund",
        detail="This action does not apply to this refund in its current state.",
        extensions={"reason": reason} | extra,
    )


async def _translate(session: AsyncSession, exc: Exception, refund_id: UUID | None) -> ApiError:
    if isinstance(exc, RefundNotFoundError):
        return not_found_error()
    if isinstance(exc, OrderNotPaidError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="ORDER_NOT_PAID",
            title="Order not paid",
            detail="Only money that was paid can be refunded.",
        )
    if isinstance(exc, RefundExceedsAvailableError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="REFUND_EXCEEDS_AVAILABLE",
            title="Refund exceeds the available balance",
            detail="An item exceeds its line's balance, or the total exceeds the payment's.",
            extensions={
                "available": {
                    "lines": [
                        {"order_item_id": str(line_id), "balance_cents": cents}
                        for line_id, cents in sorted(exc.lines.items(), key=lambda p: str(p[0]))
                    ],
                    "payment_cents": exc.payment_cents,
                }
            },
        )
    if isinstance(exc, RefundRequiresCancellationError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="REFUND_REQUIRES_CANCELLATION",
            title="Cancel the line instead",
            detail="Refunding an unfinished physical line in full needs its cancellation.",
            extensions={"order_item_ids": [str(i) for i in exc.order_item_ids]},
        )
    if isinstance(exc, RefundRefusedError):
        extra: dict[str, Any] = {}
        if exc.reason == "already_reissued" and refund_id is not None:
            row = await refund_row(session, refund_id)
            twin = row.reissued_by_refund_id if row else None
            extra["reissued_by_refund_id"] = str(twin) if twin else None
        return _invalid(exc.reason, **extra)
    raise exc


_DOMAIN = (
    RefundNotFoundError,
    OrderNotPaidError,
    RefundExceedsAvailableError,
    RefundRequiresCancellationError,
    RefundRefusedError,
)


async def _integrity_alert(
    request: Request, exc: OrderTotalMismatchError, order_id: UUID | None
) -> ApiError:
    """Q-2 (Q11): an error log and a payment alert, in their own transaction, after the
    refund's rolled back; nothing of the refund is written."""
    await logger.aerror(
        "refund_integrity_error",
        order_id=str(order_id) if order_id else None,
        payment_id=str(exc.payment_id) if exc.payment_id else None,
    )
    async with request.app.state.db_session_factory() as session, session.begin():
        await SqlPaymentAlerts(session).raise_alert(
            AlertKind.REFUND_INTEGRITY,
            payment_id=exc.payment_id,
            order_id=order_id,
            details={"reason": "order_total_mismatch"},
            dedupe_window=repeat_window(AlertKind.REFUND_INTEGRITY),
        )
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="ORDER_TOTAL_MISMATCH",
        title="Order totals do not match",
        detail="The order's total does not match its lines or its payment. Nothing was written.",
    )


async def _in_transaction(
    request: Request,
    work: Callable[[AsyncSession], Awaitable[Response]],
    *,
    order_id: UUID | None = None,
    refund_id: UUID | None = None,
) -> Response:
    """One transaction for the claim, the locks and every write; any refusal rolls it all
    back, so a 4xx stores nothing (plan 2.1)."""
    async with request.app.state.db_session_factory() as session:
        try:
            async with session.begin():
                try:
                    return await work(session)
                except _DOMAIN as exc:
                    raise await _translate(session, exc, refund_id) from exc
        except OrderTotalMismatchError as exc:
            if order_id is None and refund_id is not None:
                async with session.begin():
                    row = await refund_row(session, refund_id)
                order_id = row.order_id if row else None
            raise await _integrity_alert(request, exc, order_id) from exc


def _claim_refusal(claim: InProgress | Conflict) -> ApiError:
    if isinstance(claim, InProgress):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
            title="Request in progress",
            detail="This request is still being processed. Retry shortly with the same key.",
            headers={"Retry-After": "2"},
        )
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_KEY_CONFLICT",
        title="Idempotency key reused",
        detail="This Idempotency-Key was already used for a different request.",
    )


async def _idempotent(
    request: Request,
    session: AsyncSession,
    *,
    scope: str,
    admin_id: UUID,
    key: str,
    body: dict[str, Any],
    write: Callable[[], Awaitable[UUID]],
    detail: Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]] | None = None,
) -> Response:
    """Claim, write, then store the 201 (a refund's detail unless `detail` reads another)."""
    claims = idempotency_store(session)
    claim = await claims.claim(
        scope=scope,
        user_id=admin_id,
        key=key,
        request_hash=request_hash(scope, body),
        expires_at=datetime.now(UTC) + IDEMPOTENCY_TTL,
    )
    if isinstance(claim, Replay):  # only a 201 is ever stored here
        return JSONResponse(claim.body, status_code=claim.status_code, headers=REPLAYED)
    if isinstance(claim, InProgress | Conflict):
        raise _claim_refusal(claim)
    refund_id = await write()
    read = await (detail or _detail)(session, refund_id)
    await claims.attach(claim.record_id, resource_id=refund_id)
    await claims.complete(claim.record_id, status_code=status.HTTP_201_CREATED, body=read)
    return JSONResponse(read, status_code=status.HTTP_201_CREATED)


async def _detail(session: AsyncSession, refund_id: UUID) -> dict[str, Any]:
    row = await refund_row(session, refund_id)
    assert row is not None
    return RefundDetail.of(row).model_dump(mode="json")


@admin_router.post(
    "/orders/{order_id}/refunds",
    status_code=status.HTTP_201_CREATED,
    response_model=RefundDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Record a refund on a paid order (pay it in the provider's dashboard, then settle)",
    responses={
        **_WRITE,
        409: {
            "description": "ORDER_NOT_PAID, ORDER_TOTAL_MISMATCH, IDEMPOTENCY_KEY_CONFLICT, "
            "or IDEMPOTENCY_REQUEST_IN_PROGRESS."
        },
        422: {
            "description": "REFUND_EXCEEDS_AVAILABLE (with `available`), "
            "REFUND_REQUIRES_CANCELLATION (with `order_item_ids`), or VALIDATION_ERROR."
        },
    },
)
async def create_order_refund(
    order_id: UUID,
    body: RefundCreate,
    request: Request,
    idempotency_key: IdempotencyKey,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    items = sorted(
        (ItemFact(i.order_item_id, i.amount_cents) for i in body.items),
        key=lambda item: str(item.order_item_id),
    )
    fingerprint = {
        "order_id": str(order_id),
        "items": [[str(i.order_item_id), i.amount_cents] for i in items],
        "reason": body.reason,
    }

    async def work(session: AsyncSession) -> Response:
        async def write() -> UUID:
            outcome = await create_refund(
                refund_deps(session),
                order_id=order_id,
                kind=RefundKind.ADMIN,
                items=items,
                reason=body.reason,
                ctx=_ctx(request, claims),
                at=datetime.now(UTC),
            )
            return outcome.refund_id

        return await _idempotent(
            request,
            session,
            scope=CREATE_SCOPE,
            admin_id=claims.user_id,
            key=idempotency_key,
            body=fingerprint,
            write=write,
        )

    return await _in_transaction(request, work, order_id=order_id)


@admin_router.post(
    "/refunds/{refund_id}/reissue",
    status_code=status.HTTP_201_CREATED,
    response_model=RefundDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Reissue a failed refund as a new pending one (same kind, items and amount)",
    responses={
        **_TRANSITION,
        409: {
            "description": "INVALID_STATE_TRANSITION (`not_failed`, `already_reissued` with "
            "`reissued_by_refund_id`), ORDER_TOTAL_MISMATCH, IDEMPOTENCY_KEY_CONFLICT, or "
            "IDEMPOTENCY_REQUEST_IN_PROGRESS."
        },
    },
)
async def reissue(
    refund_id: UUID,
    request: Request,
    idempotency_key: IdempotencyKey,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    async def work(session: AsyncSession) -> Response:
        async def write() -> UUID:
            outcome = await reissue_refund(
                refund_deps(session),
                refund_id=refund_id,
                ctx=_ctx(request, claims),
                at=datetime.now(UTC),
            )
            return outcome.refund_id

        return await _idempotent(
            request,
            session,
            scope=REISSUE_SCOPE,
            admin_id=claims.user_id,
            key=idempotency_key,
            body={"refund_id": str(refund_id)},
            write=write,
        )

    return await _in_transaction(request, work, refund_id=refund_id)


async def _transition(
    request: Request, refund_id: UUID, act: Callable[[AsyncSession], Awaitable[object]]
) -> Response:
    async def work(session: AsyncSession) -> Response:
        await act(session)
        return JSONResponse(await _detail(session, refund_id))

    return await _in_transaction(request, work, refund_id=refund_id)


@admin_router.post(
    "/refunds/{refund_id}/settle",
    response_model=RefundDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Mark a pending refund paid out (after paying it in the provider's dashboard)",
    responses=_TRANSITION,
)
async def settle(
    refund_id: UUID,
    body: RefundSettlementRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    """Settling a settled refund answers 200 unchanged; no order or payment status moves."""
    return await _transition(
        request,
        refund_id,
        lambda session: settle_refund(
            refund_deps(session),
            refund_id=refund_id,
            reference=body.reference,
            note=body.note,
            ctx=_ctx(request, claims),
            at=datetime.now(UTC),
        ),
    )


@admin_router.post(
    "/refunds/{refund_id}/fail",
    response_model=RefundDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Mark a pending refund failed: it stays owed until reissued or voided",
    responses=_TRANSITION,
)
async def fail(
    refund_id: UUID,
    body: RefundFailureRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    return await _transition(
        request,
        refund_id,
        lambda session: fail_refund(
            refund_deps(session),
            refund_id=refund_id,
            reason=body.reason,
            ctx=_ctx(request, claims),
            at=datetime.now(UTC),
        ),
    )


@admin_router.post(
    "/refunds/{refund_id}/void",
    response_model=RefundDetail,
    dependencies=[Depends(require_csrf), _WRITE_LIMIT],
    summary="Close a refund created by mistake, unpaid (never after settlement)",
    responses=_TRANSITION,
)
async def void(
    refund_id: UUID,
    body: RefundVoidRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    """A second void answers 200 with the first reason; a voided refund is never reissued."""
    return await _transition(
        request,
        refund_id,
        lambda session: void_refund(
            refund_deps(session),
            refund_id=refund_id,
            reason=body.reason,
            ctx=_ctx(request, claims),
            at=datetime.now(UTC),
        ),
    )


# --- Reads: no CSRF; the admin boundary and the per-admin read limit apply -----------


def encode_cursor(created_at: datetime, refund_id: UUID) -> str:
    raw = f"{created_at.isoformat()}{_SEPARATOR}{refund_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        moment, row_id = text.split(_SEPARATOR)
        parsed = datetime.fromisoformat(moment), UUID(row_id)
        if parsed[0].tzinfo is None:
            raise ValueError("a cursor's time is always aware")
    except (ValueError, binascii.Error, UnicodeDecodeError, OverflowError) as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "not a valid cursor", "type": "value_error"}]
        ) from exc
    return parsed


@admin_router.get(
    "/refunds",
    response_model=RefundPage,
    dependencies=[_READ_LIMIT],
    summary="The obligations queue (pending or owed, oldest first), or the history",
    responses={**_RESPONSES, 422: {"description": "VALIDATION_ERROR: a bad filter or cursor."}},
)
async def list_refunds(
    session: AsyncSession = Depends(get_session),
    queue: bool = True,
    status_filter: Annotated[list[RefundStatus] | None, Query(alias="status")] = None,
    kind: Annotated[list[RefundKind] | None, Query()] = None,
    order_id: UUID | None = None,
    customer_id: UUID | None = None,
    created_from: AwareDatetime | None = None,
    created_to: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=limits.ADMIN_PAGE_MAX)] = limits.ADMIN_PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> RefundPage:
    filters = RefundFilters(
        queue=queue,
        statuses=tuple(status_filter or ()),
        kinds=tuple(kind or ()),
        order_id=order_id,
        customer_id=customer_id,
        created_from=created_from,
        created_to=created_to,
    )
    rows = await refund_page(session, filters, after=decode_cursor(cursor), limit=limit + 1)
    page = rows[:limit]
    last = page[-1] if len(rows) > limit else None
    return RefundPage(
        items=[RefundDetail.of(row) for row in page],
        next_cursor=encode_cursor(last.created_at, last.id) if last else None,
    )


@admin_router.get(
    "/refunds/{refund_id}",
    response_model=RefundDetail,
    dependencies=[_READ_LIMIT],
    summary="One refund with its items and reissue links",
    responses=_RESPONSES,
)
async def get_refund(refund_id: UUID, session: AsyncSession = Depends(get_session)) -> RefundDetail:
    row = await refund_row(session, refund_id)
    if row is None:
        raise not_found_error()
    return RefundDetail.of(row)
