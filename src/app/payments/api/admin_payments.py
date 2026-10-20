"""Admin payment actions (VS-024 plan 2.2, 2.3): reconcile (202, then the provider is
asked in a background task with no transaction open) and manual confirm (providers
without a status API only). Mounted on the admin router: admin, MFA, CSRF, limits."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
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
from app.payments.domain import limits
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.exceptions import (
    ManualConfirmRefusedError,
    PaymentNotFoundError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import ConfirmRefusal
from app.payments.domain.outcome import Outcome
from app.payments.domain.payments import Payment
from app.payments.domain.release import Capability
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.reconcile import reconcile_in_background
from app.payments.infrastructure.verification import capability
from app.platform.public import SqlAuditWriter

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

    provider_reference: Annotated[PlainStr, Field(min_length=1, max_length=255)]
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
    summary="Confirm a payment by hand from the provider's dashboard",
    responses={
        **_RESPONSES,
        409: {
            "description": "MANUAL_CONFIRMATION_NOT_ALLOWED (the provider has a status API), "
            "PAYMENT_REFERENCE_MISMATCH, or INVALID_STATE_TRANSITION (`cash_payment`)."
        },
        422: {
            "description": "PAYMENT_AMOUNT_MISMATCH (with `expected_amount_cents`, `currency`): "
            "nothing is written; or VALIDATION_ERROR."
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
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="PAYMENT_REFERENCE_MISMATCH",
            title="Provider reference mismatch",
            detail="That reference belongs to another payment, or this one has another.",
        ) from exc
    payment = await SqlPaymentStore(session).get(payment_id)
    assert payment is not None
    return ManualConfirmRead(outcome=outcome, payment=PaymentSummary.of(payment))


def _refused(exc: ManualConfirmRefusedError) -> ApiError:
    if exc.refusal is ConfirmRefusal.CASH_PAYMENT:
        return _invalid("cash_payment")
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
