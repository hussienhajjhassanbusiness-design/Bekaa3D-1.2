"""Manual confirm's refusals, as a pure table (VS-024 plan 2.3 steps 1-3, D6, D7). Nothing
is written for any refusal; a differing amount is never recorded as a late capture. Only
the `manual` provider may omit the reference (ADR-049 d5)."""

from enum import StrEnum

from app.payments.domain.enums import PaymentProvider
from app.payments.domain.release import Capability


class ConfirmRefusal(StrEnum):
    CASH_PAYMENT = "cash_payment"  # 409 INVALID_STATE_TRANSITION
    STATUS_QUERY_AVAILABLE = "status_query_available"  # 409 MANUAL_CONFIRMATION_NOT_ALLOWED
    REFERENCE_REQUIRED = "reference_required"  # 422 PAYMENT_REFERENCE_REQUIRED
    AMOUNT_MISMATCH = "amount_mismatch"  # 422 PAYMENT_AMOUNT_MISMATCH


def confirm_refusal(
    *,
    provider: PaymentProvider,
    capability: Capability,
    payment_amount_cents: int,
    typed_amount_cents: int,
    typed_currency: str,
    reference_given: bool,
) -> ConfirmRefusal | None:
    """First match wins; None means apply through `apply_result`."""
    if provider is PaymentProvider.CASH:
        return ConfirmRefusal.CASH_PAYMENT
    if capability is Capability.STATUS_QUERY:
        return ConfirmRefusal.STATUS_QUERY_AVAILABLE
    if not reference_given and provider is not PaymentProvider.MANUAL:
        return ConfirmRefusal.REFERENCE_REQUIRED
    if typed_amount_cents != payment_amount_cents or typed_currency != "USD":
        return ConfirmRefusal.AMOUNT_MISMATCH
    return None


def second_transfer(*, captured: bool, stored: str | None, typed: str | None) -> bool:
    """A-01: an attempt holding money keeps its reference; another one is a second transfer."""
    return captured and typed is not None and typed != stored


class CaptureRefusal(StrEnum):
    """Record-capture's refusals (VS-030 plan 3.6, Q5); nothing is written for any."""

    CASH_PAYMENT = "cash_payment"  # 409 INVALID_STATE_TRANSITION
    STATUS_QUERY_AVAILABLE = "status_query_available"  # 409 MANUAL_CONFIRMATION_NOT_ALLOWED
    REFERENCE_REQUIRED = "reference_required"  # 422 PAYMENT_REFERENCE_REQUIRED
    ALREADY_PAID = "already_paid"  # 409 INVALID_STATE_TRANSITION
    ALREADY_LATE_CAPTURED = "already_late_captured"  # 409 INVALID_STATE_TRANSITION
    USE_CONFIRM = "use_confirm"  # 409 INVALID_STATE_TRANSITION: a matching amount pays


def capture_refusal(
    *,
    provider: PaymentProvider,
    capability: Capability,
    reached_paid: bool,
    late_captured: bool,
    payment_amount_cents: int,
    typed_amount_cents: int,
    typed_currency: str,
    reference_given: bool,
) -> CaptureRefusal | None:
    """First match wins; None means record the mismatch as a late capture."""
    if provider is PaymentProvider.CASH:
        return CaptureRefusal.CASH_PAYMENT
    if capability is Capability.STATUS_QUERY:
        return CaptureRefusal.STATUS_QUERY_AVAILABLE
    if not reference_given and provider is not PaymentProvider.MANUAL:
        return CaptureRefusal.REFERENCE_REQUIRED
    if reached_paid:
        return CaptureRefusal.ALREADY_PAID
    if late_captured:
        return CaptureRefusal.ALREADY_LATE_CAPTURED
    if typed_amount_cents == payment_amount_cents and typed_currency == "USD":
        return CaptureRefusal.USE_CONFIRM
    return None
