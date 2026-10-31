"""`POST /api/v1/me/offers/{offer_id}/checkout` (VS-041, F-094; ADR-037). Cart checkout's
two transactions around the provider call, its idempotency, replay and rate limit; the
price is the offer's agreed amount. Contract: docs/offers.md."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.text import PlainStr
from app.catalog.public import cart_product_reader
from app.core.exceptions import ApiError
from app.core.security import hash_phone
from app.identity.public import User, not_found_error, verified_user_short_read
from app.negotiation.public import SqlOfferCheckouts
from app.ordering.api.checkout import (
    CHECKOUT_ERRORS,
    IdempotencyKey,
    announce_if_manual,
    checkout_rate_limit,
    create_payment_request,
    in_progress_error,
    key_conflict_error,
    provider_failed,
    translate_checkout_error,
)
from app.ordering.api.checkout_schemas import CheckoutRead, lebanese_phone
from app.ordering.api.idempotent import replay, stored
from app.ordering.api.problems import payment_already_active_error
from app.ordering.application.services.checkout import CheckoutCustomer
from app.ordering.application.services.offer_checkout import (
    OfferCheckoutCommand,
    place_offer_order,
)
from app.ordering.domain.exceptions import (
    OfferCheckoutExpiredError,
    OfferCheckoutNotFoundError,
    OfferNotCheckoutableError,
    OrderingDomainError,
    PaymentAlreadyActiveError,
)
from app.ordering.infrastructure.checkout_addresses import SqlCustomerAccounts
from app.ordering.infrastructure.notices import SqlOrderNotices
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.public import (
    ProviderUnavailableError,
    fail_attempt,
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

router = APIRouter(prefix="/me/offers", tags=["offers"])

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    404: {"description": "NOT_FOUND: no such offer among the caller's own."},
    409: {
        "description": "INVALID_STATE_TRANSITION (with `offer_status`), PAYMENT_ALREADY_ACTIVE "
        "(with `payment_id`, `payment_status`, `redirect_url`), PRODUCT_ALREADY_OWNED (with "
        "`product_ids`), IDEMPOTENCY_KEY_CONFLICT, or IDEMPOTENCY_REQUEST_IN_PROGRESS."
    },
    410: {"description": "OFFER_CHECKOUT_EXPIRED: the checkout window has closed."},
    422: {
        "description": "PRODUCT_NOT_PURCHASABLE (with `lines`), PAYMENT_METHOD_NOT_ALLOWED "
        "(with `reason`), CONTACT_PHONE_REQUIRED (`manual` without `contact_phone`), "
        "INVALID_FULFILLMENT (`contact_phone` for another provider), or VALIDATION_ERROR."
    },
    429: {"description": "RATE_LIMITED: shares cart checkout's hourly limit."},
    502: {
        "description": "PAYMENT_PROVIDER_UNAVAILABLE: the order exists unpaid (with "
        "`order_id`, `order_number`); replayed for the same key."
    },
    503: {"description": "ORDERS_PAUSED, or ONLINE_PAYMENT_UNAVAILABLE."},
}


class OfferCheckoutRequest(BaseModel):
    """api-endpoints.md 29.5; `payment_provider` as checkout and retry take it."""

    model_config = ConfigDict(extra="forbid")

    accept_terms: Literal[True]
    accept_digital_final_sale: Literal[True]
    payment_provider: Annotated[PlainStr, Field(min_length=1, max_length=32)] | None = None
    contact_phone: Annotated[PlainStr, Field(max_length=32)] | None = Field(
        default=None,
        description="Lebanese; required when the provider is `manual` (the administrator "
        "calls it to arrange payment), refused otherwise (VS-050 Q1).",
    )

    @field_validator("contact_phone")
    @classmethod
    def _normalise_phone(cls, value: str | None) -> str | None:
        return lebanese_phone(value)


def _translate(exc: OrderingDomainError) -> ApiError:
    if isinstance(exc, OfferCheckoutNotFoundError):
        return not_found_error()
    if isinstance(exc, OfferCheckoutExpiredError):
        return ApiError(
            status_code=status.HTTP_410_GONE,
            code="OFFER_CHECKOUT_EXPIRED",
            title="Offer checkout expired",
            detail="The checkout window for this offer has closed.",
        )
    if isinstance(exc, OfferNotCheckoutableError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_STATE_TRANSITION",
            title="Offer cannot be checked out",
            detail=f"An offer that is {exc.offer_status} cannot be checked out.",
            extensions={"offer_status": exc.offer_status},
        )
    if isinstance(exc, PaymentAlreadyActiveError):
        return payment_already_active_error(exc)
    return translate_checkout_error(exc)


_TRANSLATED = (
    OfferCheckoutNotFoundError,
    OfferCheckoutExpiredError,
    OfferNotCheckoutableError,
    PaymentAlreadyActiveError,
    *CHECKOUT_ERRORS,
)


@router.post(
    "/{offer_id}/checkout",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutRead,
    dependencies=[Depends(checkout_rate_limit)],
    summary="Place the order for an accepted offer at its agreed price and start its payment",
    responses=_RESPONSES,
)
async def checkout_offer(
    offer_id: UUID,
    request: Request,
    body: OfferCheckoutRequest,
    idempotency_key: IdempotencyKey,
    user: User = Depends(verified_user_short_read),
) -> Response:
    """Tx1: claim (scope `offer_checkout:{offer_id}`), place the order, lock and re-check
    the offer, COMMIT. The provider call with no transaction open. Tx2: the reference or
    the failure, and the stored response."""
    providers = request.app.state.payment_providers
    scope = f"offer_checkout:{offer_id}"
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
                raise await in_progress_error(session, claim)
            if isinstance(claim, Conflict):
                raise key_conflict_error()
            try:
                placed = await place_offer_order(
                    offers=SqlOfferCheckouts(session),
                    accounts=SqlCustomerAccounts(session),
                    products=await cart_product_reader(session),
                    orders=SqlOrderStore(session),
                    attempts=payment_attempts(session, providers),
                    settings=settings_reader(session),
                    audit=SqlAuditWriter(session),
                    notices=SqlOrderNotices(session),
                    customer=CheckoutCustomer(id=user.id, email=user.email),
                    command=OfferCheckoutCommand(
                        offer_id, body.payment_provider, body.contact_phone
                    ),
                    hash_phone=hash_phone,
                    now=now,
                    clock=lambda: datetime.now(UTC),
                )
            except _TRANSLATED as exc:
                raise _translate(exc) from exc
            await claims.attach(claim.record_id, resource_id=placed.order.id)
            await announce_if_manual(session, placed.order, placed.payment)

        try:
            created = await start_online_payment(
                providers[placed.payment.provider], create_payment_request(placed)
            )
        except ProviderUnavailableError:
            failed = provider_failed(request, placed)
            async with session.begin():
                await fail_attempt(
                    payment_store(session),
                    SqlAuditWriter(session),
                    payment_id=placed.payment.id,
                    order_id=placed.order.id,
                    actor_user_id=user.id,
                    at=datetime.now(UTC),
                )
                await claims.complete(
                    claim.record_id, status_code=failed.status_code, body=stored(failed)
                )
            return failed

        read = CheckoutRead.of(placed, created.redirect_url).model_dump(mode="json")
        async with session.begin():
            await record_provider_reference(
                payment_store(session),
                payment_id=placed.payment.id,
                created=created,
                at=datetime.now(UTC),
            )
            await claims.complete(claim.record_id, status_code=status.HTTP_201_CREATED, body=read)
    return JSONResponse(read, status_code=status.HTTP_201_CREATED)
