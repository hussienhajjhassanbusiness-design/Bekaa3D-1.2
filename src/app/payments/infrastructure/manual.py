"""Manual confirm (VS-024 plan 2.3) in the caller's unit of work; the route is step 12.
Only for a provider without a status API; a typed amount or currency that differs from
the attempt is refused before any lock or write, and is never a late capture."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.public import lock_order_for_change
from app.payments.domain.exceptions import (
    ManualConfirmRefusedError,
    PaymentNotFoundError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import ConfirmRefusal, confirm_refusal
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.verification import (
    Providers,
    apply_provider_result,
    capability,
)
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from app.platform.public import SqlAuditWriter

logger = structlog.get_logger()


async def confirm_payment_manually(
    session: AsyncSession,
    providers: Providers,
    payment_id: UUID,
    *,
    admin_id: UUID,
    provider_reference: str,
    amount_cents: int,
    currency: str,
    reason: str,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> Outcome:
    """Raises PaymentNotFoundError, ManualConfirmRefusedError or
    PaymentReferenceMismatchError; the caller's rollback then leaves nothing written."""
    store = SqlPaymentStore(session)
    seen = await store.get(payment_id)  # unlocked: the provider, amount and order
    if seen is None:
        raise PaymentNotFoundError(f"payment {payment_id} does not exist")
    refusal = confirm_refusal(
        provider=seen.provider,
        capability=capability(providers, seen.provider.value),
        payment_amount_cents=seen.amount_cents,
        typed_amount_cents=amount_cents,
        typed_currency=currency,
    )
    if refusal is not None:
        if refusal is ConfirmRefusal.AMOUNT_MISMATCH:
            await logger.awarning(
                "payment_manual_confirm_refused", payment_id=str(payment_id), admin_id=str(admin_id)
            )
        raise ManualConfirmRefusedError(refusal, expected_amount_cents=seen.amount_cents)
    locked = await lock_order_for_change(session, seen.order_id)  # orders, lines by id
    payment = await store.lock(payment_id)
    if locked is None or payment is None:
        raise PaymentNotFoundError(f"payment {payment_id} vanished")
    if payment.provider_payment_id not in (None, provider_reference):
        raise PaymentReferenceMismatchError("the payment has another provider reference")
    owner = await store.find_by_reference(payment.provider, provider_reference)
    if owner is not None and owner.id != payment_id:
        raise PaymentReferenceMismatchError("another payment has this provider reference")
    outcome = await apply_provider_result(
        session,
        payment_id,
        ProviderResult("paid", amount_cents, "USD"),
        source="manual",
        actor_user_id=admin_id,
        provider_payment_id=provider_reference,
    )
    marked = await SqlWebhookEventStore(session).mark_processed_for_payment(
        payment_id, at=datetime.now(UTC)
    )
    await SqlAuditWriter(session).record(
        actor_user_id=admin_id,
        action="payment.manual_confirmation",
        entity_type="payment",
        entity_id=payment_id,
        after_data={
            "order_id": str(payment.order_id),
            "order_number": locked.order.order_number,
            "typed_amount_cents": amount_cents,
            "typed_currency": currency,
            "provider_reference": provider_reference,
            "reason": reason,
            "outcome": outcome.value,
            "attempt_status_before": payment.status.value,
            "events_marked_processed": marked,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return outcome
