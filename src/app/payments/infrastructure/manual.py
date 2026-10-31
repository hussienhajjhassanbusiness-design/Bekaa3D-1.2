"""Manual confirm (VS-024 plan 2.3) in the caller's unit of work; the route is step 12.
Only for a provider without a status API; a typed amount or currency that differs from
the attempt is refused before any lock or write. `manual` may omit the reference (ADR-049)."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.public import lock_order_for_change
from app.payments.domain.exceptions import (
    CaptureRecordRefusedError,
    ManualConfirmRefusedError,
    PaymentNotFoundError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import (
    CaptureRefusal,
    ConfirmRefusal,
    capture_refusal,
    confirm_refusal,
)
from app.payments.domain.outcome import REACHED_PAID, Outcome, ProviderResult
from app.payments.domain.payments import Payment
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
    provider_reference: str | None,
    amount_cents: int,
    currency: str,
    reason: str,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> Outcome:
    """Raises PaymentNotFoundError, ManualConfirmRefusedError or
    PaymentReferenceMismatchError; the caller's rollback then leaves nothing written."""
    provider_reference = (provider_reference or "").strip() or None  # case kept (ADR-049)
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
        reference_given=provider_reference is not None,
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
    if provider_reference is not None:
        await _require_own_reference(store, payment, provider_reference)
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


async def record_capture_manually(
    session: AsyncSession,
    providers: Providers,
    payment_id: UUID,
    *,
    admin_id: UUID,
    amount_cents: int,
    currency: str,
    dashboard_reference: str | None,
    reason: str,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> Outcome:
    """VS-024 Q2 / VS-030 Q5: a capture the dashboard shows and no status API can report,
    whose amount or currency differs from the attempt, recorded as a late capture through
    `apply_result`, so the alert and the refund obligation come with it."""
    dashboard_reference = (dashboard_reference or "").strip() or None
    store = SqlPaymentStore(session)
    seen = await store.get(payment_id)  # unlocked: the provider, state and amount
    if seen is None:
        raise PaymentNotFoundError(f"payment {payment_id} does not exist")
    refusal = capture_refusal(
        provider=seen.provider,
        capability=capability(providers, seen.provider.value),
        reached_paid=seen.status in REACHED_PAID,
        late_captured=seen.late_captured_at is not None,
        payment_amount_cents=seen.amount_cents,
        typed_amount_cents=amount_cents,
        typed_currency=currency,
        reference_given=dashboard_reference is not None,
    )
    if refusal is not None:
        raise CaptureRecordRefusedError(refusal)
    outcome = await apply_provider_result(
        session,
        payment_id,
        ProviderResult("paid", amount_cents, currency),
        source="manual",
        actor_user_id=admin_id,
    )
    if outcome not in (Outcome.LATE_CAPTURE, Outcome.LATE_CAPTURE_AND_FAIL):
        raise CaptureRecordRefusedError(CaptureRefusal.ALREADY_LATE_CAPTURED)  # moved meanwhile
    marked = await SqlWebhookEventStore(session).mark_processed_for_payment(
        payment_id, at=datetime.now(UTC)
    )
    await SqlAuditWriter(session).record(
        actor_user_id=admin_id,
        action="payment.capture_recorded",
        entity_type="payment",
        entity_id=payment_id,
        after_data={
            "order_id": str(seen.order_id),
            "typed_amount_cents": amount_cents,
            "typed_currency": currency,
            "dashboard_reference": dashboard_reference,
            "reason": reason,
            "outcome": outcome.value,
            "attempt_status_before": seen.status.value,
            "events_marked_processed": marked,
        },
        request_id=request_id,
        ip_hash=ip_hash,
    )
    return outcome


async def _require_own_reference(store: SqlPaymentStore, payment: Payment, reference: str) -> None:
    """Unique per provider when given; `uq_payments_provider_reference` is the backstop."""
    if payment.provider_payment_id not in (None, reference):
        raise PaymentReferenceMismatchError("the payment has another provider reference")
    await store.lock_reference(payment.provider, reference)
    owner = await store.find_by_reference(payment.provider, reference)
    if owner is not None and owner.id != payment.id:
        raise PaymentReferenceMismatchError("another payment has this provider reference")
