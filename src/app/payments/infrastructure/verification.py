"""Verification (VS-023 plan 2.4, 3.6). Tx A reads without locks; the provider is asked
with no transaction open; Tx B applies the provider's own answer. The webhook body is
never trusted: it only says which payment to ask about."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.payments.application.ports import PaymentProviderPort, PaymentRef, ProviderStatus
from app.payments.application.services.apply import Source, apply_result
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.domain.limits import PROVIDER_TIMEOUT_SECONDS, VERIFY_BATCH_SIZE
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure.ordering_side import SqlOrderSide, SqlPaymentNotices
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.webhook_events import (
    MANUAL_CONFIRMATION_REQUIRED,
    PROVIDER_UNKNOWN_REFERENCE,
    SqlWebhookEventStore,
)
from app.platform.public import SqlAuditWriter

logger = structlog.get_logger()

BATCH_SIZE = VERIFY_BATCH_SIZE
Providers = Mapping[str, PaymentProviderPort]
Factory = async_sessionmaker[AsyncSession]


async def apply_provider_result(
    session: AsyncSession,
    payment_id: UUID,
    result: ProviderResult,
    *,
    source: Source,
    actor_user_id: UUID | None,
    provider_payment_id: str | None = None,
) -> Outcome:
    """Tx B on the caller's session: orders, lines by id, payments (ADR-024 d9)."""
    return await apply_result(
        payments=SqlPaymentStore(session),
        orders=SqlOrderSide(session),
        audit=SqlAuditWriter(session),
        notices=SqlPaymentNotices(session),
        payment_id=payment_id,
        result=result,
        source=source,
        actor_user_id=actor_user_id,
        provider_payment_id=provider_payment_id,
        at=datetime.now(UTC),
    )


def _queryable(adapter: PaymentProviderPort) -> bool:
    # An adapter that does not declare the flag keeps VS-023's behaviour: it is asked.
    return bool(getattr(adapter, "supports_status_query", True))


async def _ask(providers: Providers, provider: str, ref: PaymentRef) -> ProviderStatus:
    """Bounded at PROVIDER_TIMEOUT_SECONDS; every failure to answer is ProviderUnavailableError."""
    adapter = providers.get(provider)
    if adapter is None:
        raise ProviderUnavailableError(f"provider {provider!r} is not configured")
    if not _queryable(adapter):
        raise ProviderUnavailableError(f"provider {provider!r} has no status query")
    try:
        async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
            return await adapter.query_status(ref)
    except TimeoutError as exc:
        raise ProviderUnavailableError(f"provider {provider!r} status query timed out") from exc


async def verify_event(factory: Factory, providers: Providers, event_id: UUID) -> Outcome | None:
    """None when the event is gone or processed, or nothing was learned: the event then keeps
    a `processing_error` (retried by the cron, except manual confirmation) (VS-024 3.3)."""
    async with factory() as session, session.begin():
        event = await SqlWebhookEventStore(session).get(event_id)
        if event is None or event.processed_at is not None or event.payment_id is None:
            return None
        payment = await SqlPaymentStore(session).get(event.payment_id)
    if payment is None:
        return None
    adapter = providers.get(payment.provider.value)
    if adapter is not None and not _queryable(adapter):
        await _leave_unprocessed(factory, event_id, MANUAL_CONFIRMATION_REQUIRED)
        await logger.awarning(
            "payment_manual_confirmation_due", event_id=str(event_id), payment_id=str(payment.id)
        )
        return None
    try:
        status = await _ask(
            providers, payment.provider.value, PaymentRef(payment.id, payment.provider_payment_id)
        )
    except ProviderUnavailableError as exc:
        await _leave_unprocessed(factory, event_id, str(exc))
        await logger.awarning("payment_verification_deferred", event_id=str(event_id))
        return None
    if status.result.state == "unknown":
        await _leave_unprocessed(factory, event_id, PROVIDER_UNKNOWN_REFERENCE)
        await logger.awarning(
            "payment_reference_unknown", event_id=str(event_id), payment_id=str(payment.id)
        )
        return None
    async with factory() as session, session.begin():
        outcome = await apply_provider_result(
            session,
            payment.id,
            status.result,
            source="webhook",
            actor_user_id=None,
            provider_payment_id=status.provider_payment_id,
        )
        await SqlWebhookEventStore(session).mark_processed(event_id, at=datetime.now(UTC))
    return outcome


async def _leave_unprocessed(factory: Factory, event_id: UUID, error: str) -> None:
    async with factory() as session, session.begin():
        await SqlWebhookEventStore(session).record_error(event_id, error)


async def verify_payment(
    factory: Factory,
    providers: Providers,
    payment_id: UUID,
    *,
    source: Literal["reconcile", "release", "manual_reconcile"] = "reconcile",
    actor_user_id: UUID | None = None,
) -> Outcome:
    """The same without an event (reconciliation). Raises ProviderUnavailableError when the
    provider does not answer; `unknown` is NOOP and opens no Tx B (VS-024 3.2a)."""
    async with factory() as session, session.begin():
        payment = await SqlPaymentStore(session).get(payment_id)
    if payment is None:
        return Outcome.NOOP
    status = await _ask(
        providers, payment.provider.value, PaymentRef(payment.id, payment.provider_payment_id)
    )
    if status.result.state == "unknown":
        await logger.awarning("payment_reference_unknown", payment_id=str(payment.id))
        return Outcome.NOOP
    async with factory() as session, session.begin():
        return await apply_provider_result(
            session,
            payment.id,
            status.result,
            source=source,
            actor_user_id=actor_user_id,
            provider_payment_id=status.provider_payment_id,
        )


async def verify_unprocessed(
    factory: Factory, providers: Providers, *, limit: int = BATCH_SIZE
) -> dict[str, int]:
    """The `verify_payments` cron body: the oldest unprocessed events, one at a time."""
    async with factory() as session, session.begin():
        ids = await SqlWebhookEventStore(session).unprocessed_ids(limit)
    counts: dict[str, int] = {"seen": len(ids), "applied": 0, "deferred": 0}
    for event_id in ids:
        outcome = await verify_event(factory, providers, event_id)
        counts["applied" if outcome is not None else "deferred"] += 1
    return counts


async def verify_in_background(factory: Any, providers: Providers, event_id: UUID) -> None:
    """Runs after the webhook's 200. A failure is logged and left to the cron."""
    try:
        await verify_event(factory, providers, event_id)
    except Exception:
        await logger.aexception("payment_background_verification_failed", event_id=str(event_id))
