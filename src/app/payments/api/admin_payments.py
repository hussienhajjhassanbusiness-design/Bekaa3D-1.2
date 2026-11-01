"""Admin payment actions (VS-024 plan 2.2, 2.3): reconcile (202, then the provider is
asked in a background task with no transaction open) and manual confirm (providers
without a status API only). Mounted on the admin router: admin, MFA, CSRF, limits."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import text
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
from app.ordering.public import (
    Holds,
    Order,
    OrderStatus,
    PaymentMethod,
    hold_deadline,
    manual_release_refusal,
    order_lines,
    orders_by_id,
    read_holds,
)
from app.payments.api.admin_refunds import IdempotencyKey, _idempotent
from app.payments.domain import limits
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.exceptions import (
    CaptureRecordRefusedError,
    ManualConfirmRefusedError,
    PaymentNotFoundError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import CaptureRefusal, ConfirmRefusal
from app.payments.domain.outcome import LIVE, Outcome
from app.payments.domain.payments import Payment
from app.payments.domain.release import Capability
from app.payments.infrastructure.admin_reads import (
    AdminPaymentRow,
    PaymentFilters,
    payment_events,
    payment_page,
    payment_row,
)
from app.payments.infrastructure.manual import confirm_payment_manually, record_capture_manually
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.reconcile import reconcile_in_background
from app.payments.infrastructure.release import release_window
from app.payments.infrastructure.verification import capability
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from app.platform.public import SqlAuditWriter, audit_history, settings_reader

admin_router = APIRouter(prefix="/payments", tags=["admin"], route_class=AdminBoundaryRoute)

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."},
    403: {"description": "CSRF_INVALID."},
    404: {"description": "NOT_FOUND: no such payment (customers always get this)."},
    429: {"description": "RATE_LIMITED: this action's per-administrator hourly limit."},
}


class PaymentSummary(BaseModel):
    """No provider metadata (so no redirect URL), event payloads or customer email."""

    id: UUID
    order_id: UUID
    provider: PaymentProvider
    status: str
    amount_cents: int
    currency: str
    captured_amount_cents: int | None
    captured_currency: str | None
    provider_payment_id: str | None
    initiated_at: datetime | None
    late_captured_at: datetime | None

    @classmethod
    def of(cls, payment: Payment) -> Self:
        return cls(
            id=payment.id,
            order_id=payment.order_id,
            provider=payment.provider,
            status=payment.status.value,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            captured_amount_cents=payment.captured_amount_cents,
            captured_currency=payment.captured_currency,
            provider_payment_id=payment.provider_payment_id,
            initiated_at=payment.initiated_at,
            late_captured_at=payment.late_captured_at,
        )


class ReconcileQueued(BaseModel):
    payment: PaymentSummary
    reconcile: Literal["queued"] = "queued"


class ManualPaymentConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_reference: Annotated[PlainStr, Field(min_length=1, max_length=255)] | None = Field(
        default=None,
        description="The transfer's own reference; optional for `manual` only, unique per "
        "provider when given (ADR-049). Notes go in `reason`.",
    )
    verified_amount_cents: Annotated[int, Field(ge=0)]
    verified_currency: Annotated[PlainStr, Field(min_length=3, max_length=3)] = "USD"
    reason: Annotated[
        MultilineStr, Field(min_length=limits.REASON_MIN, max_length=limits.REASON_MAX)
    ]


class ManualConfirmRead(BaseModel):
    outcome: Outcome
    payment: PaymentSummary


def _limit(prefix: str, limit: int) -> Any:
    """Per administrator per hour, on top of the admin router's 300/min (plan 3.8)."""

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


def audit_context(request: Request) -> tuple[str | None, str | None]:
    ip = client_ip(request)
    return getattr(request.state, "request_id", None), hash_ip(ip) if ip else None


def _invalid(reason: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="INVALID_STATE_TRANSITION",
        title="Not allowed for this payment",
        detail="This action does not apply to this payment.",
        extensions={"reason": reason},
    )


@admin_router.post(
    "/{payment_id}/reconcile",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReconcileQueued,
    dependencies=[
        Depends(require_csrf),
        Depends(_limit("admin_payment_reconcile", limits.RECONCILE_RATE_LIMIT)),
    ],
    summary="Ask the provider about a payment, after answering 202",
    responses={
        **_RESPONSES,
        409: {"description": "INVALID_STATE_TRANSITION (`reason`: `cash_payment`)."},
        503: {"description": "PAYMENT_VERIFICATION_UNAVAILABLE: the provider has no status API."},
    },
)
async def reconcile_payment(
    payment_id: UUID,
    request: Request,
    background: BackgroundTasks,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ReconcileQueued:
    """Nothing here calls the provider. The unit of work commits before the 202 is sent;
    Starlette runs the task only after the body (plan 2.2 steps 3-5)."""
    payment = await SqlPaymentStore(session).get(payment_id)  # unlocked
    if payment is None:
        raise not_found_error()
    if payment.provider is PaymentProvider.CASH:
        raise _invalid("cash_payment")
    providers = request.app.state.payment_providers
    if capability(providers, payment.provider.value) is not Capability.STATUS_QUERY:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="PAYMENT_VERIFICATION_UNAVAILABLE",
            title="Payment verification unavailable",
            detail="This payment's provider cannot be asked; confirm it manually instead.",
        )
    request_id, ip_hash = audit_context(request)
    await SqlAuditWriter(session).record(
        actor_user_id=claims.user_id,
        action="payment.reconcile_requested",
        entity_type="payment",
        entity_id=payment.id,
        after_data={"order_id": str(payment.order_id)},
        request_id=request_id,
        ip_hash=ip_hash,
    )
    background.add_task(
        reconcile_in_background,
        request.app.state.db_session_factory,
        providers,
        payment.id,
        claims.user_id,
    )
    return ReconcileQueued(payment=PaymentSummary.of(payment))


@admin_router.post(
    "/{payment_id}/confirm",
    response_model=ManualConfirmRead,
    dependencies=[
        Depends(require_csrf),
        Depends(_limit("admin_payment_confirm", limits.CONFIRM_RATE_LIMIT)),
    ],
    summary="Confirm a payment by hand: from the provider's dashboard, or as arranged (`manual`)",
    responses={
        **_RESPONSES,
        409: {
            "description": "MANUAL_CONFIRMATION_NOT_ALLOWED (the provider has a status API), "
            "PAYMENT_REFERENCE_MISMATCH, or INVALID_STATE_TRANSITION (`cash_payment`)."
        },
        422: {
            "description": "PAYMENT_AMOUNT_MISMATCH (with `expected_amount_cents`, `currency`): "
            "nothing is written; PAYMENT_REFERENCE_REQUIRED (no reference, not `manual`); "
            "or VALIDATION_ERROR."
        },
    },
)
async def confirm_payment(
    payment_id: UUID,
    body: ManualPaymentConfirmRequest,
    request: Request,
    claims: AccessTokenClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ManualConfirmRead:
    request_id, ip_hash = audit_context(request)
    try:
        outcome = await confirm_payment_manually(
            session,
            request.app.state.payment_providers,
            payment_id,
            admin_id=claims.user_id,
            provider_reference=body.provider_reference,
            amount_cents=body.verified_amount_cents,
            currency=body.verified_currency,
            reason=body.reason,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    except PaymentNotFoundError as exc:
        raise not_found_error() from exc
    except ManualConfirmRefusedError as exc:
        raise _refused(exc) from exc
    except PaymentReferenceMismatchError as exc:
        raise _reference_mismatch() from exc
    payment = await SqlPaymentStore(session).get(payment_id)
    assert payment is not None
    return ManualConfirmRead(outcome=outcome, payment=PaymentSummary.of(payment))


class RecordCaptureRequest(BaseModel):
    """What the dashboard shows captured, when it differs from the attempt (VS-030 Q5)."""

    model_config = ConfigDict(extra="forbid")

    captured_amount_cents: Annotated[int, Field(gt=0, le=limits.REFUND_MAX_AMOUNT_CENTS)]
    captured_currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    dashboard_reference: Annotated[PlainStr, Field(min_length=1, max_length=255)] | None = Field(
        default=None, description="Optional for `manual` only (ADR-049)."
    )
    reason: Annotated[
        MultilineStr, Field(min_length=limits.REASON_MIN, max_length=limits.REASON_MAX)
    ]


class RecordCaptureRead(BaseModel):
    outcome: Outcome
    payment: PaymentSummary
    refund_id: UUID | None = Field(description="The late-capture obligation it created.")


RECORD_CAPTURE_SCOPE = "admin_record_capture"
_LIVE_LATE_REFUND = text(
    "SELECT id FROM refunds WHERE payment_id = :p AND kind = 'late_capture'"
    " AND status NOT IN ('failed', 'voided')"
)


@admin_router.post(
    "/{payment_id}/record-capture",
    status_code=status.HTTP_201_CREATED,
    response_model=RecordCaptureRead,
    dependencies=[
        Depends(require_csrf),
        Depends(_limit("admin_payment_record_capture", limits.CONFIRM_RATE_LIMIT)),
    ],
    summary="Record a capture the dashboard shows but the attempt's amount does not match",
    responses={
        **_RESPONSES,
        409: {
            "description": "MANUAL_CONFIRMATION_NOT_ALLOWED (the provider has a status API), "
            "INVALID_STATE_TRANSITION (`reason`: `cash_payment`, `already_paid`, "
            "`already_late_captured`, `use_confirm` for a matching amount), "
            "PAYMENT_REFERENCE_MISMATCH (a `manual` reference another payment has), "
            "IDEMPOTENCY_KEY_CONFLICT or IDEMPOTENCY_REQUEST_IN_PROGRESS."
        },
        422: {
            "description": "PAYMENT_REFERENCE_REQUIRED (no reference, not `manual`), or "
            "VALIDATION_ERROR."
        },
    },
)
async def record_capture(
    payment_id: UUID,
    body: RecordCaptureRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    claims: AccessTokenClaims = Depends(require_admin),
) -> Response:
    """A late capture plus its refund obligation (VS-024 Q2, VS-030 Q5): the admin then pays
    it back in the dashboard and settles it. A mistaken one is voided."""
    request_id, ip_hash = audit_context(request)
    outcome: list[Outcome] = []

    async def write(session: AsyncSession) -> UUID:
        outcome.append(
            await record_capture_manually(
                session,
                request.app.state.payment_providers,
                payment_id,
                admin_id=claims.user_id,
                amount_cents=body.captured_amount_cents,
                currency=body.captured_currency,
                dashboard_reference=body.dashboard_reference,
                reason=body.reason,
                request_id=request_id,
                ip_hash=ip_hash,
            )
        )
        return payment_id

    async def detail(session: AsyncSession, _: UUID) -> dict[str, Any]:
        payment = await SqlPaymentStore(session).get(payment_id)
        assert payment is not None
        refund_id = await session.scalar(_LIVE_LATE_REFUND, {"p": payment_id})
        read = RecordCaptureRead(
            outcome=outcome[0], payment=PaymentSummary.of(payment), refund_id=refund_id
        )
        return read.model_dump(mode="json")

    async with request.app.state.db_session_factory() as session, session.begin():
        try:
            return await _idempotent(
                request,
                session,
                scope=RECORD_CAPTURE_SCOPE,
                admin_id=claims.user_id,
                key=idempotency_key,
                body={"payment_id": str(payment_id)} | body.model_dump(mode="json"),
                write=lambda: write(session),
                detail=detail,
            )
        except PaymentNotFoundError as exc:
            raise not_found_error() from exc
        except CaptureRecordRefusedError as exc:
            raise _capture_refused(exc) from exc
        except PaymentReferenceMismatchError as exc:
            raise _reference_mismatch() from exc


def _reference_mismatch() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="PAYMENT_REFERENCE_MISMATCH",
        title="Provider reference mismatch",
        detail="That reference belongs to another payment, or this one has another.",
    )


def _reference_required() -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="PAYMENT_REFERENCE_REQUIRED",
        title="Reference required",
        detail="Only a manual payment may be confirmed without the provider's reference.",
    )


def _capture_refused(exc: CaptureRecordRefusedError) -> ApiError:
    if exc.refusal is CaptureRefusal.REFERENCE_REQUIRED:
        return _reference_required()
    if exc.refusal is CaptureRefusal.STATUS_QUERY_AVAILABLE:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="MANUAL_CONFIRMATION_NOT_ALLOWED",
            title="Manual recording not allowed",
            detail="This provider can be asked; reconcile the payment instead.",
        )
    return _invalid(str(exc.refusal))


def _refused(exc: ManualConfirmRefusedError) -> ApiError:
    if exc.refusal is ConfirmRefusal.CASH_PAYMENT:
        return _invalid("cash_payment")
    if exc.refusal is ConfirmRefusal.REFERENCE_REQUIRED:
        return _reference_required()
    if exc.refusal is ConfirmRefusal.STATUS_QUERY_AVAILABLE:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="MANUAL_CONFIRMATION_NOT_ALLOWED",
            title="Manual confirmation not allowed",
            detail="This provider can be asked; reconcile the payment instead.",
        )
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="PAYMENT_AMOUNT_MISMATCH",
        title="Amount does not match",
        detail="The confirmed amount must equal the attempt's amount in USD.",
        extensions={"expected_amount_cents": exc.expected_amount_cents, "currency": "USD"},
    )


# --- Reads (plan 2.2): read-only, so no CSRF; the admin boundary and its 300/min apply ---

_SEPARATOR = "|"


class AdminPaymentRead(BaseModel):
    """No provider metadata (so no redirect URL), event payloads or customer email."""

    id: UUID
    order_id: UUID
    order_number: str | None
    provider: PaymentProvider
    status: PaymentStatus
    amount_cents: int
    currency: str
    captured_amount_cents: int | None
    captured_currency: str | None
    provider_payment_id: str | None
    initiated_at: datetime
    verified_at: datetime | None
    failed_at: datetime | None
    expired_at: datetime | None
    late_captured_at: datetime | None
    needs_manual_confirmation: bool
    unprocessed_event_count: int
    hold_expires_at: datetime | None = Field(
        description="A live attempt on an unpaid order: when the order is released. The "
        "customer's contact is on `GET /admin/orders/{order_id}`."
    )

    @classmethod
    def of(cls, row: AdminPaymentRow, order: Order | None, holds: Holds) -> Self:
        expires = None
        if order is not None and row.status in LIVE and order.status is OrderStatus.PENDING_PAYMENT:
            hold = holds.for_provider(row.provider.value)
            expires = hold_deadline(order.placed_at, row.initiated_at, hold)
        number = order.order_number if order is not None else None
        return cls(**vars(row), order_number=number, hold_expires_at=expires)


class AdminPaymentPage(BaseModel):
    items: list[AdminPaymentRead]
    next_cursor: str | None = Field(description="Opaque; pass back as `cursor`. Null at the end.")


class AdminPaymentOrderRead(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    total_cents: int
    currency: str
    placed_at: datetime
    cancelled_at: datetime | None
    hold_expires_at: datetime | None
    manual_release_available_at: datetime | None


class AdminPaymentEventRead(BaseModel):
    id: UUID
    event_type: str | None
    signature_valid: bool | None
    received_at: datetime
    processed_at: datetime | None
    processing_error: str | None


class AdminPaymentHistoryRead(BaseModel):
    action: str
    actor_user_id: UUID | None
    created_at: datetime
    data: dict[str, Any] | None


class AdminPaymentDetail(BaseModel):
    payment: AdminPaymentRead
    order: AdminPaymentOrderRead
    events: list[AdminPaymentEventRead]
    history: list[AdminPaymentHistoryRead]
    available_actions: list[Literal["reconcile", "confirm", "release_order"]]


def encode_cursor(initiated_at: datetime, payment_id: UUID) -> str:
    raw = f"{initiated_at.isoformat()}{_SEPARATOR}{payment_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    """Exactly the `(initiated_at, id)` encoded; anything else is a 422 on `cursor`."""
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
    response_model=AdminPaymentPage,
    summary="List payments, oldest first (`late_captured=true`: the refunds to make; "
    "`awaiting_confirmation=true`: the `manual` payments to arrange and confirm)",
    responses={**_RESPONSES, 422: {"description": "VALIDATION_ERROR: a bad filter or cursor."}},
)
async def list_payments(
    session: AsyncSession = Depends(get_session),
    status_filter: Annotated[list[PaymentStatus] | None, Query(alias="status")] = None,
    provider: PaymentProvider | None = None,
    order_id: UUID | None = None,
    late_captured: bool | None = None,
    awaiting_confirmation: bool = False,
    initiated_after: AwareDatetime | None = None,
    initiated_before: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=limits.ADMIN_PAGE_MAX)] = limits.ADMIN_PAGE_DEFAULT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> AdminPaymentPage:
    filters = PaymentFilters(
        statuses=tuple(status_filter or ()),
        provider=provider,
        order_id=order_id,
        late_captured=late_captured,
        initiated_after=initiated_after,
        initiated_before=initiated_before,
        awaiting_confirmation=awaiting_confirmation,
    )
    rows = await payment_page(session, filters, after=decode_cursor(cursor), limit=limit + 1)
    page = rows[:limit]
    orders = await orders_by_id(session, sorted({row.order_id for row in page}, key=str))
    holds = await read_holds(settings_reader(session))
    items = [AdminPaymentRead.of(row, orders.get(row.order_id), holds) for row in page]
    last = page[-1] if len(rows) > limit else None
    return AdminPaymentPage(
        items=items, next_cursor=encode_cursor(last.initiated_at, last.id) if last else None
    )


@admin_router.get(
    "/{payment_id}",
    response_model=AdminPaymentDetail,
    summary="One payment: its order, events (without payloads), history and actions",
    responses=_RESPONSES,
)
async def get_payment(
    payment_id: UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> AdminPaymentDetail:
    row = await payment_row(session, payment_id)
    if row is None:
        raise not_found_error()
    order = (await orders_by_id(session, [row.order_id]))[row.order_id]
    attempts = await SqlPaymentStore(session).for_order(order.id)
    latest = max(attempts, key=lambda p: (p.initiated_at, p.id), default=None)
    deadline = available_at = None
    holds = await read_holds(settings_reader(session))
    if order.payment_method is PaymentMethod.ONLINE and order.status is OrderStatus.PENDING_PAYMENT:
        deadline, available_at = await release_window(session, order.placed_at, latest, holds)
    events = await payment_events(session, payment_id)
    history = await audit_history(
        session, entity_type="payment", entity_id=payment_id, limit=limits.ADMIN_PAGE_MAX
    )
    able = capability(request.app.state.payment_providers, row.provider.value)
    actions: list[Literal["reconcile", "confirm", "release_order"]] = []
    if row.provider is not PaymentProvider.CASH:
        actions.append("reconcile" if able is Capability.STATUS_QUERY else "confirm")
    if available_at is not None:
        pending = await SqlWebhookEventStore(session).count_unprocessed_for_payments(
            [p.id for p in attempts]
        )
        refusal = manual_release_refusal(
            order,
            await order_lines(session, order.id),
            now=datetime.now(UTC),
            available_at=available_at,
            unprocessed_events=pending,
            events_reviewed=True,
        )
        if refusal is None:
            actions.append("release_order")
    return AdminPaymentDetail(
        payment=AdminPaymentRead.of(row, order, holds),
        order=AdminPaymentOrderRead(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            total_cents=order.total_cents,
            currency=order.currency,
            placed_at=order.placed_at,
            cancelled_at=order.cancelled_at,
            hold_expires_at=deadline,
            manual_release_available_at=available_at,
        ),
        events=[AdminPaymentEventRead(**vars(event)) for event in events],
        history=[
            AdminPaymentHistoryRead(
                action=entry.action,
                actor_user_id=entry.actor_user_id,
                created_at=entry.created_at,
                data=entry.after_data,
            )
            for entry in history
        ],
        available_actions=actions,
    )
