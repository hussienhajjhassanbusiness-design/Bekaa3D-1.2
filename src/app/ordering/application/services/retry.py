"""Retry's first transaction (VS-024 plan 2.1, T1). In the caller's session after the
idempotency claim; never commits and never calls the provider. Locks the caller's own
`orders` row, then an offer order's offer (VS-041); the attempt is an INSERT in a SAVEPOINT."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.ordering.application.ports import (
    OfferCheckouts,
    OrderStore,
    PaymentAttemptRef,
    PaymentAttempts,
)
from app.ordering.domain.checkout_rules import choose_provider
from app.ordering.domain.exceptions import (
    LiveAttemptExistsError,
    OfferCheckoutExpiredError,
    OfferNotCheckoutableError,
    OnlinePaymentUnavailableError,
    PaymentAlreadyActiveError,
    RetryOrderNotFoundError,
    RetryRefusedError,
)
from app.ordering.domain.orders import Order, OrderLine
from app.ordering.domain.payment_recovery import RetryRefusal, hold_deadline, retry_refusal
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class RetriedPayment:
    order: Order
    payment: PaymentAttemptRef
    hold_expires_at: datetime


async def start_retry(
    *,
    orders: OrderStore,
    attempts: PaymentAttempts,
    audit: AuditWriter,
    user_id: UUID,
    order_id: UUID,
    requested_provider: str | None,
    hold: timedelta,
    now: datetime,
    offers: OfferCheckouts,
    clock: Callable[[], datetime],
) -> RetriedPayment:
    """Raises RetryOrderNotFoundError, RetryRefusedError, OnlinePaymentUnavailableError,
    PaymentMethodNotAllowedError or PaymentAlreadyActiveError; the caller rolls back."""
    order = await orders.lock_owned_order(order_id, user_id)
    if order is None:
        raise RetryOrderNotFoundError(str(order_id))
    lines = await orders.order_lines(order_id)
    refusal = retry_refusal(order, lines, now=now, hold=hold)
    if refusal is not None:
        raise RetryRefusedError(refusal.value)
    await _require_open_offer(offers, lines, user_id=user_id, clock=clock)
    configured = attempts.configured_providers()
    if not configured:
        raise OnlinePaymentUnavailableError("No online payment provider is configured.")
    if (live := await attempts.live_attempt(order_id)) is not None:
        raise already_active(live)
    provider = choose_provider(
        requested_provider, configured, await attempts.previous_provider(order_id)
    )
    try:
        payment = await attempts.open_retry_attempt(
            order_id=order_id,
            amount_cents=order.total_cents,
            currency=order.currency,
            provider=provider,
            at=now,
        )
    except LiveAttemptExistsError as exc:  # appeared since the read above
        live = await attempts.live_attempt(order_id)
        raise already_active(live) from exc
    await audit.record(
        actor_user_id=user_id,
        action="payment.retry_started",
        entity_type="payment",
        entity_id=payment.id,
        after_data={"order_id": str(order_id), "payment_id": str(payment.id), "provider": provider},
    )
    return RetriedPayment(order, payment, hold_deadline(order.placed_at, now, hold))


async def _require_open_offer(
    offers: OfferCheckouts,
    lines: Sequence[OrderLine],
    *,
    user_id: UUID,
    clock: Callable[[], datetime],
) -> None:
    """An offer order is paid only inside its window (ADR-037): orders, then the offer."""
    for offer_id in sorted({line.offer_id for line in lines if line.offer_id}, key=str):
        try:
            await offers.lock(offer_id, user_id, clock=clock)
        except (OfferCheckoutExpiredError, OfferNotCheckoutableError) as exc:
            raise RetryRefusedError(RetryRefusal.OFFER_CHECKOUT_EXPIRED.value) from exc


def already_active(live: PaymentAttemptRef | None) -> PaymentAlreadyActiveError:
    """`redirect_url` only for a `pending` attempt: a `processing` one has nothing to resume."""
    if live is None:
        return PaymentAlreadyActiveError(None, None, None)
    url = live.redirect_url if live.status == "pending" else None
    return PaymentAlreadyActiveError(live.id, live.status, url)
