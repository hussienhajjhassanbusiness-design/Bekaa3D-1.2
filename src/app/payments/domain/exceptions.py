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
