"""Starting an online payment (VS-023 plan 3.6, 3.8). The checkout route commits Tx1,
calls `start_online_payment` with no transaction open, then records the answer in Tx2."""

from datetime import datetime
from uuid import UUID

from app.payments.application.ports import (
    CreatedPayment,
    CreatePayment,
    PaymentProviderPort,
    PaymentStore,
)
from app.platform.application.ports import AuditWriter


async def start_online_payment(
    provider: PaymentProviderPort, request: CreatePayment
) -> CreatedPayment:
    """The provider call; raises ProviderUnavailableError. No session, so no lock."""
    return await provider.create_payment(request)


async def record_provider_reference(
    payments: PaymentStore, *, payment_id: UUID, created: CreatedPayment, at: datetime
) -> None:
    """Tx2 success: only the new attempt's row (plan 8.1, Checkout Tx2)."""
    await payments.set_provider_reference(
        payment_id, created.provider_payment_id, redirect_url=created.redirect_url, at=at
    )


async def fail_attempt(
    payments: PaymentStore,
    audit: AuditWriter,
    *,
    payment_id: UUID,
    order_id: UUID,
    actor_user_id: UUID,
    at: datetime,
) -> None:
    """Tx2 after a provider failure (Q14): the attempt fails; the order stays unpaid."""
    await payments.mark_failed(payment_id, at=at)
    await audit.record(
        actor_user_id=actor_user_id,
        action="payment.failed",
        entity_type="payment",
        entity_id=payment_id,
        after_data={"order_id": str(order_id), "reason": "provider_unavailable"},
    )
