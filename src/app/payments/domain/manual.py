"""Manual confirm's refusals, as a pure table (VS-024 plan 2.3 steps 1-3, D6, D7). Nothing
is written for any refusal; a differing amount is never recorded as a late capture."""

from enum import StrEnum

from app.payments.domain.enums import PaymentProvider
from app.payments.domain.release import Capability


class ConfirmRefusal(StrEnum):
    CASH_PAYMENT = "cash_payment"  # 409 INVALID_STATE_TRANSITION
    STATUS_QUERY_AVAILABLE = "status_query_available"  # 409 MANUAL_CONFIRMATION_NOT_ALLOWED
    AMOUNT_MISMATCH = "amount_mismatch"  # 422 PAYMENT_AMOUNT_MISMATCH


def confirm_refusal(
    *,
    provider: PaymentProvider,
    capability: Capability,
    payment_amount_cents: int,
    typed_amount_cents: int,
    typed_currency: str,
) -> ConfirmRefusal | None:
    """First match wins; None means apply through `apply_result`."""
    if provider is PaymentProvider.CASH:
        return ConfirmRefusal.CASH_PAYMENT
    if capability is Capability.STATUS_QUERY:
        return ConfirmRefusal.STATUS_QUERY_AVAILABLE
    if typed_amount_cents != payment_amount_cents or typed_currency != "USD":
        return ConfirmRefusal.AMOUNT_MISMATCH
    return None
