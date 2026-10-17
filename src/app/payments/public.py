"""Payments' published surface (frozen at VS-023 Checkpoint 2). Another context imports
from here or from `app.payments.application.ports` only; callers type against the ports."""

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.application.ports import (
    CreatedPayment,
    CreatePayment,
    PaymentProviderPort,
)
from app.payments.application.services.payments import (
    fail_attempt,
    record_provider_reference,
    start_online_payment,
)
from app.payments.domain.exceptions import PaymentConfigurationError, ProviderUnavailableError
from app.payments.domain.outcome import ProviderResult
from app.payments.infrastructure.payments import SqlPaymentAttempts, SqlPaymentStore
from app.payments.infrastructure.providers.factory import configured_payment_providers

__all__ = [
    "CreatePayment",
    "CreatedPayment",
    "PaymentConfigurationError",
    "PaymentProviderPort",
    "ProviderResult",
    "ProviderUnavailableError",
    "configured_payment_providers",
    "fail_attempt",
    "payment_attempts",
    "payment_store",
    "record_provider_reference",
    "start_online_payment",
]


def payment_attempts(
    session: AsyncSession, providers: Mapping[str, PaymentProviderPort]
) -> SqlPaymentAttempts:
    """Ordering's `PaymentAttempts` port on the caller's session (checkout Tx1)."""
    return SqlPaymentAttempts(session, providers)


def payment_store(session: AsyncSession) -> SqlPaymentStore:
    """The payment repository on the caller's session (checkout Tx2)."""
    return SqlPaymentStore(session)
