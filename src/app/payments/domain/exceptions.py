from datetime import datetime
from enum import StrEnum
from uuid import UUID


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


class CashAlreadyRecordedError(PaymentsDomainError):
    """`uq_payments_one_cash` refused a second cash payment on one order (VS-029)."""


class OrderNotPaidError(PaymentsDomainError):
    """409 ORDER_NOT_PAID: no payment of the order reached paid (VS-030 L0)."""


class OrderTotalMismatchError(PaymentsDomainError):
    """409 ORDER_TOTAL_MISMATCH (Q-2): an integrity fault; nothing written, logged, alerted."""

    def __init__(
        self,
        *,
        order_total_cents: int,
        line_total_cents: int,
        payment_amount_cents: int,
        payment_id: UUID | None = None,
    ) -> None:
        super().__init__("order total does not match its lines or its payment")
        self.order_total_cents, self.line_total_cents = order_total_cents, line_total_cents
        self.payment_amount_cents, self.payment_id = payment_amount_cents, payment_id


class RefundExceedsAvailableError(PaymentsDomainError):
    """422 REFUND_EXCEEDS_AVAILABLE with the balance per line and for the payment (L4)."""

    def __init__(self, *, lines: dict[UUID, int], payment_cents: int) -> None:
        super().__init__("refund exceeds the available balance")
        self.lines, self.payment_cents = lines, payment_cents


class RefundRequiresCancellationError(PaymentsDomainError):
    """422 REFUND_REQUIRES_CANCELLATION: the item empties an unfinished physical line (L5)."""

    def __init__(self, order_item_ids: tuple[UUID, ...]) -> None:
        super().__init__("a full refund of an unfinished physical line needs a cancellation")
        self.order_item_ids = order_item_ids


class RefundNotFoundError(PaymentsDomainError):
    """404: no such refund, order, or order line (a line of another order included)."""


class RefundRefusedError(PaymentsDomainError):
    """409 INVALID_STATE_TRANSITION with a stable `reason` (VS-030 plan 2.3, 2.4)."""

    def __init__(self, reason: str, *, reissued_by: UUID | None = None) -> None:
        super().__init__(reason)
        self.reason, self.reissued_by = reason, reissued_by


class OrderLockRequiredError(PaymentsDomainError):
    """A refund fact read by a transaction that does not hold the order's row lock."""


class ChargebackNotOnlineError(PaymentsDomainError):
    """422 CHARGEBACK_NOT_ONLINE: a cash payment has no card network to charge it back."""


class ChargebackDuplicateError(PaymentsDomainError):
    """409 CHARGEBACK_DUPLICATE: this provider dispute reference is already recorded."""


class ChargebackItemsForbiddenError(PaymentsDomainError):
    """422 CHARGEBACK_ITEMS_FORBIDDEN: a late-captured attempt paid no line."""


class ChargebackAllocationInvalidError(PaymentsDomainError):
    """422 CHARGEBACK_ALLOCATION_INVALID: an item over its line's balance, or the items over
    the payment's balance or over what the bank charged beyond the absorbed refunds."""

    def __init__(
        self, *, lines: dict[UUID, int], payment_cents: int, chargeable_cents: int
    ) -> None:
        super().__init__("chargeback items exceed the available balance")
        self.lines, self.payment_cents = lines, payment_cents
        self.chargeable_cents = chargeable_cents
