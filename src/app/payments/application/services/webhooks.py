"""Storing a webhook event (VS-023 plan 2.2; SRS 9.2). The route has already capped the
body and checked the signature; nothing here changes a payment or calls the provider."""

from datetime import datetime
from uuid import UUID

import structlog

from app.payments.application.ports import (
    NewWebhookEvent,
    ParsedEvent,
    PaymentStore,
    WebhookEventStore,
)
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.payments import Payment

logger = structlog.get_logger()


async def _resolve(
    payments: PaymentStore, provider: PaymentProvider, event: ParsedEvent
) -> tuple[Payment | None, str | None]:
    """The provider's reference first, then our `payments.id` (the Tx2-crash case,
    Revision 5 item 1). Returns the payment, or None with the reason it was ignored."""
    if event.provider_payment_id is not None:
        found = await payments.find_by_reference(provider, event.provider_payment_id)
        if found is not None:
            return found, None
    if event.payment_reference is None:
        return None, "unknown_payment"
    found = await payments.get(event.payment_reference)
    if found is None:
        return None, "unknown_payment"
    if found.provider is not provider:
        return None, "provider_mismatch"
    if (
        event.provider_payment_id is not None
        and found.provider_payment_id is not None
        and found.provider_payment_id != event.provider_payment_id
    ):
        return None, "reference_mismatch"
    return found, None


async def receive_webhook(
    *,
    payments: PaymentStore,
    events: WebhookEventStore,
    provider: PaymentProvider,
    event: ParsedEvent,
    signature_valid: bool,
    at: datetime,
) -> UUID | None:
    """INSERT ... ON CONFLICT (provider, provider_event_id) DO NOTHING. Returns the new
    event's id for verification, or None for a duplicate or an event stored as ignored."""
    payment, ignored = await _resolve(payments, provider, event)
    event_id = await events.insert_if_new(
        NewWebhookEvent(
            provider=provider,
            provider_event_id=event.event_id,
            event_type=event.event_type,
            payload=event.payload,
            signature_valid=signature_valid,
            provider_payment_id=event.provider_payment_id,
            payment_id=payment.id if payment is not None else None,
            processing_error=ignored,
            processed_at=at if ignored is not None else None,
        )
    )
    if ignored is not None:
        await logger.aerror(
            "payment_webhook_ignored",
            provider=provider.value,
            provider_event_id=event.event_id,
            reason=ignored,
        )
        return None
    return event_id
