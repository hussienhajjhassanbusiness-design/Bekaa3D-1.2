from datetime import datetime
from enum import StrEnum


class PaymentsDomainError(Exception):
    """Base for payments-context errors; routers map them to stable codes."""


class PaymentConfigurationError(PaymentsDomainError):
    """`PAYMENT_PROVIDER` names no adapter allowed in this environment (refuses boot)."""


class ProviderUnavailableError(PaymentsDomainError):
    """The provider timed out, refused or answered garbage; nothing is known."""


class InvalidSignatureError(PaymentsDomainError):
    """A webhook body whose signature does not verify; never stored."""


class MalformedEventError(PaymentsDomainError):
    """A signed webhook body the adapter cannot read."""


class PaymentNotFoundError(PaymentsDomainError):
    """The payment (or its order) to apply a result to does not exist."""


class OrderNotFoundError(PaymentsDomainError):
    """The order to release does not exist (404)."""


class ManualReleaseRefusedError(PaymentsDomainError):
    """409 INVALID_STATE_TRANSITION with `reason` (plan 2.5 step 5); nothing written."""

    def __init__(self, reason: str, *, available_at: datetime, unprocessed_events: int) -> None:
        super().__init__(reason)
        self.reason, self.available_at = reason, available_at
        self.unprocessed_events = unprocessed_events


class ManualConfirmRefusedError(PaymentsDomainError):
    """A `ConfirmRefusal` (plan 2.3 steps 1-3); nothing written."""

    def __init__(self, refusal: StrEnum, *, expected_amount_cents: int) -> None:
        super().__init__(refusal.value)
        self.refusal, self.expected_amount_cents = refusal, expected_amount_cents


class PaymentReferenceMismatchError(PaymentsDomainError):
    """409 PAYMENT_REFERENCE_MISMATCH: the typed reference is another payment's or differs."""
