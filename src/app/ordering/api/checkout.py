"""`POST /api/v1/checkout` (VS-023 plan 2.1, 3.8). Two transactions with the provider
call between them, so no lock or transaction is held across the network. Only 201 and
the post-commit 502 are stored for replay; any other refusal rolls the claim back."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import problem_response
from app.catalog.public import cart_product_reader
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_phone
from app.identity.public import User, verified_user_short_read
from app.ordering.api.checkout_schemas import (
    IDEMPOTENCY_KEY_PATTERN,
    CheckoutRead,
    CheckoutRequest,
)
from app.ordering.api.idempotent import replay, stored
from app.ordering.api.problems import already_owned_error
from app.ordering.application.services.checkout import (
    CheckoutCustomer,
    OnlinePlacedOrder,
    PlacedOrder,
    place_order,
)
from app.ordering.domain.exceptions import (
    CartEmptyError,
    CartPriceChangedError,
    CashLimitReachedError,
    CashNotAvailableError,
    CheckoutLinesRefusedError,
    ConsentRequiredError,
    CustomerAccountClosedError,
    InvalidFulfillmentError,
    OnlinePaymentUnavailableError,
    OrderingDomainError,
    OrdersPausedError,
    PaymentMethodNotAllowedError,
    ProductAlreadyOwnedError,
)
from app.ordering.infrastructure.carts import SqlCartStore
from app.ordering.infrastructure.cash import SqlCashChecks
from app.ordering.infrastructure.checkout_addresses import (
    SqlCheckoutAddresses,
    SqlCustomerAccounts,
)
from app.ordering.infrastructure.notices import SqlOrderNotices
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.public import (
    CHECKOUT_RATE_LIMIT,
    CHECKOUT_RATE_WINDOW_SECONDS,
    CreatePayment,
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

router = APIRouter(prefix="/checkout", tags=["checkout"])

SCOPE = "checkout"
_RATE_LIMIT = CHECKOUT_RATE_LIMIT
_RATE_WINDOW_SECONDS = CHECKOUT_RATE_WINDOW_SECONDS

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description="8-255 characters of [A-Za-z0-9._:-]; one key per checkout attempt.",
    ),
]

_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session cookie was presented."},
    403: {"description": "CSRF token missing or invalid, or EMAIL_VERIFICATION_REQUIRED."},
    409: {
        "description": "CART_EMPTY (with `dropped_lines`), CART_PRICE_CHANGED (with "
        "`price_changes`), PRODUCT_ALREADY_OWNED, IDEMPOTENCY_KEY_CONFLICT, or "
        "IDEMPOTENCY_REQUEST_IN_PROGRESS (with `order_id`, `order_number`)."
    },
    422: {
        "description": "PRODUCT_NOT_PURCHASABLE or QUANTITY_EXCEEDS_LIMIT (with `lines`), "
        "INVALID_FULFILLMENT, PAYMENT_METHOD_NOT_ALLOWED or CASH_PAYMENT_LIMIT_REACHED (each "
        "with `reason`), CASH_NOT_AVAILABLE (no reason: a block or an open cash order on the "
        "account or the phone, never saying which), or VALIDATION_ERROR."
    },
    429: {"description": "RATE_LIMITED: too many checkouts this hour."},
    502: {
        "description": "PAYMENT_PROVIDER_UNAVAILABLE: the order exists unpaid (with "
        "`order_id`, `order_number`); replayed for the same key."
    },
    503: {"description": "ORDERS_PAUSED, or ONLINE_PAYMENT_UNAVAILABLE."},
}


async def checkout_rate_limit(
    request: Request, response: Response, user: User = Depends(verified_user_short_read)
) -> None:
    """Per user, fail closed, like the cart's (plan Q17). A replay counts too."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="checkout",
        subject=str(user.id),
        limit=_RATE_LIMIT,
        window_seconds=_RATE_WINDOW_SECONDS,
    )


_CONSENT_MESSAGES = {
    "accept_digital_final_sale": "STL purchases are final sale and must be accepted.",
    "accept_cash_terms": "The cash payment terms must be accepted.",
}


def translate_checkout_error(exc: OrderingDomainError) -> ApiError:
    unprocessable = status.HTTP_422_UNPROCESSABLE_ENTITY
    if isinstance(exc, CustomerAccountClosedError):
        return ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            title="Authentication required",
            detail="A valid session is required for this request.",
        )
    if isinstance(exc, CartEmptyError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="CART_EMPTY",
            title="Cart is empty",
            detail="The cart has nothing left to check out.",
            extensions={
                "dropped_lines": [
                    {"product_id": str(p), "reason": "already_owned"} for p in exc.dropped
                ]
            },
        )
    if isinstance(exc, CartPriceChangedError):
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="CART_PRICE_CHANGED",
            title="Prices changed",
            detail="Some prices changed. Accept the new prices to check out; nothing was charged.",
            extensions={
                "price_changes": [
                    {
                        "product_id": str(c.product_id),
                        "old_amount_cents": c.old_amount_cents,
                        "new_amount_cents": c.new_amount_cents,
                        "currency": c.currency,
                    }
                    for c in exc.changes
                ]
            },
        )
    if isinstance(exc, ProductAlreadyOwnedError):
        return already_owned_error(exc.product_ids)
    if isinstance(exc, CheckoutLinesRefusedError):
        lines = [
            {"product_id": str(r.product_id), "reason": r.reason}
            | ({"max_quantity": r.max_quantity} if r.max_quantity is not None else {})
            for r in exc.refusals
        ]
        if exc.only_caps:
            return ApiError(
                status_code=unprocessable,
                code="QUANTITY_EXCEEDS_LIMIT",
                title="Quantity exceeds the limit",
                detail="Some lines are above their product's limit.",
                extensions={"lines": lines},
            )
        return ApiError(
            status_code=unprocessable,
            code="PRODUCT_NOT_PURCHASABLE",
            title="Some products cannot be bought online",
            detail="Some lines cannot be bought right now.",
            extensions={"lines": lines},
        )
    if isinstance(exc, InvalidFulfillmentError):
        return ApiError(
            status_code=unprocessable,
            code="INVALID_FULFILLMENT",
            title="Fulfillment not available",
            detail="The delivery or pickup details do not fit this order.",
        )
    if isinstance(exc, CashLimitReachedError):
        return ApiError(
            status_code=unprocessable,
            code="CASH_PAYMENT_LIMIT_REACHED",
            title="Cash payment limit reached",
            detail="This order cannot be paid in cash right now.",
            extensions={"reason": exc.reason},
        )
    if isinstance(exc, CashNotAvailableError):
        return ApiError(
            status_code=unprocessable,
            code="CASH_NOT_AVAILABLE",
            title="Cash on delivery not available",
            detail="Cash on delivery isn't available for this order; please pay online.",
        )
    if isinstance(exc, PaymentMethodNotAllowedError):
        return ApiError(
            status_code=unprocessable,
            code="PAYMENT_METHOD_NOT_ALLOWED",
            title="Payment method not allowed",
            detail="This payment method cannot be used for this order.",
            extensions={"reason": exc.reason},
        )
    if isinstance(exc, ConsentRequiredError):
        return ApiError(
            status_code=unprocessable,
            code="VALIDATION_ERROR",
            title="Request body failed validation",
            detail="One or more fields failed validation.",
            errors=[
                {
                    "loc": ["body", exc.field],
                    "msg": _CONSENT_MESSAGES[exc.field],
                    "type": "missing",
                }
            ],
        )
    if isinstance(exc, OrdersPausedError):
        return ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ORDERS_PAUSED",
            title="Orders are paused",
            detail="The shop is not accepting orders right now.",
        )
    if isinstance(exc, OnlinePaymentUnavailableError):
        return ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="ONLINE_PAYMENT_UNAVAILABLE",
            title="Online payment unavailable",
            detail="Online payment is not available right now.",
        )
    raise exc


CHECKOUT_ERRORS = (
    CustomerAccountClosedError,
    CartEmptyError,
    CartPriceChangedError,
    ProductAlreadyOwnedError,
    CheckoutLinesRefusedError,
    InvalidFulfillmentError,
    PaymentMethodNotAllowedError,
    ConsentRequiredError,
    CashLimitReachedError,
    CashNotAvailableError,
    OrdersPausedError,
    OnlinePaymentUnavailableError,
)


async def in_progress_error(session: AsyncSession, claim: InProgress) -> ApiError:
    order_id = claim.resource_id
    number = await SqlOrderStore(session).order_number(order_id) if order_id else None
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
        title="Request in progress",
        detail="This checkout is still being processed. Retry shortly with the same key.",
        headers={"Retry-After": "2"},
        extensions={"order_id": str(order_id) if order_id else None, "order_number": number},
    )


def key_conflict_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_KEY_CONFLICT",
        title="Idempotency key reused",
        detail="This Idempotency-Key was already used for a different checkout request.",
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutRead,
    dependencies=[Depends(checkout_rate_limit)],
    summary="Place an order from the cart: start its online payment, or place it as cash",
    responses=_RESPONSES,
)
async def checkout(
    request: Request,
    body: CheckoutRequest,
    idempotency_key: IdempotencyKey,
    user: User = Depends(verified_user_short_read),
) -> Response:
    """Tx1 claims, places the order and attaches it; cash completes the claim there. Online
    then calls the provider with no transaction open, and Tx2 stores the reference or fails
    the attempt (docs/checkout.md). No dependency holds a session."""
    providers = request.app.state.payment_providers
    digest = request_hash(SCOPE, body.model_dump(mode="json"))
    now = datetime.now(UTC)
    async with request.app.state.db_session_factory() as session:
        async with session.begin():
            claims = idempotency_store(session)
            claim = await claims.claim(
                scope=SCOPE,
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
                placed = await place_order(
                    carts=SqlCartStore(session),
                    products=await cart_product_reader(session),
                    orders=SqlOrderStore(session),
                    attempts=payment_attempts(session, providers),
                    addresses=SqlCheckoutAddresses(session),
                    accounts=SqlCustomerAccounts(session),
                    cash=SqlCashChecks(session),
                    notices=SqlOrderNotices(session),
                    settings=settings_reader(session),
                    audit=SqlAuditWriter(session),
                    customer=CheckoutCustomer(id=user.id, email=user.email),
                    command=body.command(),
                    hash_phone=hash_phone,
                    now=now,
                )
            except CHECKOUT_ERRORS as exc:
                raise translate_checkout_error(exc) from exc
            await claims.attach(claim.record_id, resource_id=placed.order.id)
            if placed.payment is None:
                read = CheckoutRead.of(placed).model_dump(mode="json")
                await claims.complete(
                    claim.record_id, status_code=status.HTTP_201_CREATED, body=read
                )
                return JSONResponse(read, status_code=status.HTTP_201_CREATED)

        online = OnlinePlacedOrder(placed.order, placed.lines, placed.payment, placed.dropped)
        try:
            created = await start_online_payment(
                providers[online.payment.provider], create_payment_request(online)
            )
        except ProviderUnavailableError:
            failed = provider_failed(request, online)
            async with session.begin():
                await fail_attempt(
                    payment_store(session),
                    SqlAuditWriter(session),
                    payment_id=online.payment.id,
                    order_id=online.order.id,
                    actor_user_id=user.id,
                    at=datetime.now(UTC),
                )
                await claims.complete(
                    claim.record_id, status_code=failed.status_code, body=stored(failed)
                )
            return failed

        read = CheckoutRead.of(online, created.redirect_url).model_dump(mode="json")
        async with session.begin():
            await record_provider_reference(
                payment_store(session),
                payment_id=online.payment.id,
                created=created,
                at=datetime.now(UTC),
            )
            await claims.complete(claim.record_id, status_code=status.HTTP_201_CREATED, body=read)
    return JSONResponse(read, status_code=status.HTTP_201_CREATED)


def create_payment_request(placed: OnlinePlacedOrder) -> CreatePayment:
    number = placed.order.order_number
    return CreatePayment(
        payment_id=placed.payment.id,
        order_number=number,
        amount_cents=placed.payment.amount_cents,
        currency=placed.payment.currency,
        return_url=f"{get_settings().frontend_base_url.rstrip('/')}/checkout/return?order={number}",
    )


def provider_failed(request: Request, placed: PlacedOrder) -> JSONResponse:
    return problem_response(
        request,
        status_code=status.HTTP_502_BAD_GATEWAY,
        code="PAYMENT_PROVIDER_UNAVAILABLE",
        title="Payment provider unavailable",
        detail="Your order was placed but its payment could not be started. Retry payment "
        "from your order.",
        extensions={"order_id": str(placed.order.id), "order_number": placed.order.order_number},
    )
