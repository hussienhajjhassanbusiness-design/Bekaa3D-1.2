"""`POST /api/v1/me/orders/{order_id}/payments` (VS-024 plan 2.1): a new attempt for the
caller's own unpaid order. Two transactions with the provider call between them, as
checkout; `redirect_url` reaches only the owner's 201 or 409, never a log or audit row."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import problem_response
from app.api.text import PlainStr
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.identity.public import User, not_found_error, verified_user_short_read
from app.negotiation.public import SqlOfferCheckouts
from app.ordering.api.checkout_schemas import IDEMPOTENCY_KEY_PATTERN
from app.ordering.api.idempotent import replay, stored
from app.ordering.api.problems import payment_already_active_error
from app.ordering.application.services.retry import RetriedPayment, start_retry
from app.ordering.domain.enums import OrderStatus
from app.ordering.domain.exceptions import (
    OnlinePaymentUnavailableError,
    PaymentAlreadyActiveError,
    PaymentMethodNotAllowedError,
    RetryOrderNotFoundError,
    RetryRefusedError,
)
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.public import (
    CreatePayment,
    ProviderUnavailableError,
    fail_attempt,
    limits,
    payment_attempts,
    payment_store,
    record_provider_reference,
    start_online_payment,
)
from app.platform.public import (
    IDEMPOTENCY_TTL,
    Conflict,
    InProgress,
    Replay,
    SqlAuditWriter,
    idempotency_store,
    request_hash,
    settings_reader,
)

router = APIRouter(prefix="/me/orders", tags=["orders"])

HOLD_SETTING = "checkout_hold_period"

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description="8-255 characters of [A-Za-z0-9._:-]; one key per retry of one order.",
    ),
]

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    404: {"description": "NOT_FOUND: no such order, or not yours."},
    409: {
        "description": "PAYMENT_ALREADY_ACTIVE (with `payment_id`, `payment_status`, "
        "`redirect_url`), INVALID_STATE_TRANSITION (with `reason`, including "
        "`offer_checkout_expired`), IDEMPOTENCY_KEY_CONFLICT, or "
        "IDEMPOTENCY_REQUEST_IN_PROGRESS."
    },
    422: {"description": "PAYMENT_METHOD_NOT_ALLOWED (with `reason`), or VALIDATION_ERROR."},
    429: {"description": "RATE_LIMITED: too many retries this hour."},
    502: {
        "description": "PAYMENT_PROVIDER_UNAVAILABLE: the attempt failed and the order is "
        "still payable; replayed for the same key."
    },
    503: {"description": "ONLINE_PAYMENT_UNAVAILABLE."},
}


class PaymentRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_provider: Annotated[PlainStr, Field(min_length=1, max_length=32)] | None = None


class RetryOrderRead(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    total_cents: int
    currency: str
    hold_expires_at: datetime


class RetryPaymentRead(BaseModel):
    id: UUID
    status: str
    provider: str
    amount_cents: int
    currency: str
    redirect_url: str | None = Field(description="The provider's payment page; null if none.")


class PaymentRetryRead(BaseModel):
    order: RetryOrderRead
    payment: RetryPaymentRead

    @classmethod
    def of(cls, retried: RetriedPayment, redirect_url: str | None) -> Self:
        order, payment = retried.order, retried.payment
        return cls(
            order=RetryOrderRead(
                id=order.id,
                order_number=order.order_number,
                status=order.status,
                total_cents=order.total_cents,
                currency=order.currency,
                hold_expires_at=retried.hold_expires_at,
            ),
            payment=RetryPaymentRead(
                id=payment.id,
                status=payment.status,
                provider=payment.provider,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                redirect_url=redirect_url,
            ),
        )


async def _retry_rate_limit(
    request: Request, response: Response, user: User = Depends(verified_user_short_read)
) -> None:
    """Per user, fail closed, like checkout's. A replay counts too."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="payment_retry",
        subject=str(user.id),
        limit=limits.RETRY_RATE_LIMIT,
        window_seconds=limits.RETRY_RATE_WINDOW_SECONDS,
    )


def _translate(exc: Exception) -> ApiError:
    if isinstance(exc, RetryOrderNotFoundError):
        return not_found_error()
    if isinstance(exc, PaymentAlreadyActiveError):
        return payment_already_active_error(exc)
    if isinstance(exc, RetryRefusedError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Payment cannot be retried",
            detail="This order cannot take a new payment.",
            extensions={"reason": exc.reason},
        )
    if isinstance(exc, PaymentMethodNotAllowedError):
        return ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="PAYMENT_METHOD_NOT_ALLOWED",
            title="Payment method not allowed",
            detail="This payment method cannot be used for this order.",
            extensions={"reason": exc.reason},
        )
    if isinstance(exc, OnlinePaymentUnavailableError):
        return ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ONLINE_PAYMENT_UNAVAILABLE",
            title="Online payment unavailable",
            detail="Online payment is not available right now.",
        )
    raise exc


_TRANSLATED = (
    RetryOrderNotFoundError,
    PaymentAlreadyActiveError,
    RetryRefusedError,
    PaymentMethodNotAllowedError,
    OnlinePaymentUnavailableError,
)


async def _in_progress(session: AsyncSession, claim: InProgress) -> ApiError:
    number = (
        await SqlOrderStore(session).order_number(claim.resource_id) if claim.resource_id else None
    )
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
        title="Request in progress",
        detail="This retry is still being processed. Retry shortly with the same key.",
        headers={"Retry-After": "2"},
        extensions={
            "order_id": str(claim.resource_id) if claim.resource_id else None,
            "order_number": number,
        },
    )


def _conflict() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_KEY_CONFLICT",
        title="Idempotency key reused",
        detail="This Idempotency-Key was already used for a different retry request.",
    )


@router.post(
    "/{order_id}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentRetryRead,
    dependencies=[Depends(_retry_rate_limit)],
    summary="Start a new payment attempt for one of your unpaid orders",
    responses=_RESPONSES,
)
async def retry_payment(
    order_id: UUID,
    request: Request,
    body: PaymentRetryRequest,
    idempotency_key: IdempotencyKey,
    user: User = Depends(verified_user_short_read),
) -> Response:
    """Tx1: claim (scope `payment_retry:{order_id}`), lock the caller's order, T1, the new
    attempt in a SAVEPOINT, COMMIT. The provider call with no transaction open. Tx2:
    the reference or the failure, and the stored response."""
    providers = request.app.state.payment_providers
    scope = f"payment_retry:{order_id}"
    digest = request_hash(scope, body.model_dump(mode="json"))
    now = datetime.now(UTC)
    async with request.app.state.db_session_factory() as session:
        async with session.begin():
            claims = idempotency_store(session)
            claim = await claims.claim(
                scope=scope,
                user_id=user.id,
                key=idempotency_key,
                request_hash=digest,
                expires_at=now + IDEMPOTENCY_TTL,
            )
            if isinstance(claim, Replay):
                return replay(request, claim)
            if isinstance(claim, InProgress):
                raise await _in_progress(session, claim)
            if isinstance(claim, Conflict):
                raise _conflict()
            hold = await settings_reader(session).get_duration_seconds(HOLD_SETTING)
            try:
                retried = await start_retry(
                    orders=SqlOrderStore(session),
                    attempts=payment_attempts(session, providers),
                    audit=SqlAuditWriter(session),
                    user_id=user.id,
                    order_id=order_id,
                    requested_provider=body.payment_provider,
                    hold=timedelta(seconds=hold),
                    now=now,
                    offers=SqlOfferCheckouts(session),
                    clock=lambda: datetime.now(UTC),
                )
            except _TRANSLATED as exc:
                raise _translate(exc) from exc
            await claims.attach(claim.record_id, resource_id=order_id)

        try:
            created = await start_online_payment(
                providers[retried.payment.provider], _create_request(retried)
            )
        except ProviderUnavailableError:
            failed = _provider_failed(request, retried)
            async with session.begin():
                await fail_attempt(
                    payment_store(session),
                    SqlAuditWriter(session),
                    payment_id=retried.payment.id,
                    order_id=order_id,
                    actor_user_id=user.id,
                    at=datetime.now(UTC),
                )
                await claims.complete(
                    claim.record_id, status_code=failed.status_code, body=stored(failed)
                )
            return failed

        read = PaymentRetryRead.of(retried, created.redirect_url).model_dump(mode="json")
        async with session.begin():
            await record_provider_reference(
                payment_store(session),
                payment_id=retried.payment.id,
                created=created,
                at=datetime.now(UTC),
            )
            await claims.complete(claim.record_id, status_code=status.HTTP_201_CREATED, body=read)
    return JSONResponse(read, status_code=status.HTTP_201_CREATED)


def _create_request(retried: RetriedPayment) -> CreatePayment:
    number = retried.order.order_number
    return CreatePayment(
        payment_id=retried.payment.id,
        order_number=number,
        amount_cents=retried.payment.amount_cents,
        currency=retried.payment.currency,
        return_url=f"{get_settings().frontend_base_url.rstrip('/')}/checkout/return?order={number}",
    )


def _provider_failed(request: Request, retried: RetriedPayment) -> JSONResponse:
    return problem_response(
        request,
        status_code=status.HTTP_502_BAD_GATEWAY,
        code="PAYMENT_PROVIDER_UNAVAILABLE",
        title="Payment provider unavailable",
        detail="The payment could not be started. Your order is still unpaid; try again.",
        extensions={
            "order_id": str(retried.order.id),
            "order_number": retried.order.order_number,
        },
    )
