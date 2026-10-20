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
from app.payments.domain import limits
from app.payments.domain.exceptions import (
    ManualReleaseRefusedError,
    OrderNotFoundError,
    PaymentConfigurationError,
    ProviderUnavailableError,
)
from app.payments.domain.limits import CHECKOUT_RATE_LIMIT, CHECKOUT_RATE_WINDOW_SECONDS
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.payments import SqlPaymentAttempts, SqlPaymentStore
from app.payments.infrastructure.providers.factory import configured_payment_providers
from app.payments.infrastructure.reconcile import reconcile_stuck
from app.payments.infrastructure.release import release_order_by_admin, release_stale
from app.payments.infrastructure.verification import (
    apply_provider_result,
    verify_event,
    verify_payment,
    verify_unprocessed,
)

__all__ = [
    "CHECKOUT_RATE_LIMIT",
    "CHECKOUT_RATE_WINDOW_SECONDS",
    "CreatePayment",
    "CreatedPayment",
    "ManualReleaseRefusedError",
    "OrderNotFoundError",
    "Outcome",
    "PaymentConfigurationError",
    "PaymentProviderPort",
    "ProviderResult",
    "ProviderUnavailableError",
    "apply_provider_result",
    "configured_payment_providers",
    "confirm_payment_manually",
    "fail_attempt",
    "limits",
    "payment_attempts",
    "payment_store",
    "reconcile_stuck",
    "record_provider_reference",
    "release_order_by_admin",
    "release_stale",
    "start_online_payment",
    "verify_event",
    "verify_payment",
    "verify_unprocessed",
]


def payment_attempts(
    session: AsyncSession, providers: Mapping[str, PaymentProviderPort]
) -> SqlPaymentAttempts:
    """Ordering's `PaymentAttempts` port on the caller's session (checkout Tx1)."""
    return SqlPaymentAttempts(session, providers)


def payment_store(session: AsyncSession) -> SqlPaymentStore:
    """The payment repository on the caller's session (checkout Tx2)."""
    return SqlPaymentStore(session)
