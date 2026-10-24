"""What one verified provider result does to a payment (SRS 9.2, 20.1; ADR-024 d15).
Pure: the decision table is the whole of payment-state logic; writers only apply it."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.payments.domain.enums import PaymentStatus

# `unknown`: the provider has no record of the merchant reference (VS-024 D10).
ProviderState = Literal["pending", "processing", "paid", "failed", "expired", "unknown"]

LIVE = frozenset({PaymentStatus.PENDING, PaymentStatus.PROCESSING})
REACHED_PAID = frozenset(
    {PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
)


@dataclass(frozen=True)
class ProviderResult:
    """The provider's own answer to a status query, never the callback's claim."""

    state: ProviderState
    captured_amount_cents: int | None
    currency: str | None


_CURRENCY = re.compile(r"[A-Z]{3}")
MAX_CAPTURE_CENTS = 10**12  # the backfill's bound too


def readable_currency(raw: str | None) -> str | None:
    """An ISO-shaped code, uppercased; anything else is unknown."""
    code = (raw or "").strip().upper()
    return code if _CURRENCY.fullmatch(code) else None


def stored_capture(result: ProviderResult) -> tuple[int | None, str | None]:
    """What `ck_payments_captured_shape` (and a BIGINT) can hold of a capture: a negative or
    absurd amount is unknown, and an unknown amount stores no currency (VS-030 Q6 default)."""
    amount = result.captured_amount_cents
    if amount is None or not 0 <= amount <= MAX_CAPTURE_CENTS:
        return None, None
    return amount, readable_currency(result.currency)


class Outcome(StrEnum):
    APPLY_PAID = "apply_paid"
    MARK_PROCESSING = "mark_processing"
    MARK_FAILED = "mark_failed"
    MARK_EXPIRED = "mark_expired"
    LATE_CAPTURE = "late_capture"
    LATE_CAPTURE_AND_FAIL = "late_capture_and_fail"
    NOOP = "noop"


def decide(
    *,
    payment_status: PaymentStatus,
    payment_amount_cents: int,
    order_total_cents: int,
    order_cancelled: bool,
    already_late_captured: bool,
    result: ProviderResult,
) -> Outcome:
    """Paid only for a live attempt on an uncancelled order whose captured amount equals
    both the attempt and the order total in USD; any other capture is a late capture.
    `unknown` is "no answer": it never fails, pays or releases anything (VS-024 3.2a)."""
    if result.state == "unknown":
        return Outcome.NOOP
    if result.state == "paid":
        if payment_status in REACHED_PAID:
            return Outcome.NOOP
        if payment_status in LIVE:
            exact = (
                result.captured_amount_cents == payment_amount_cents == order_total_cents
                and result.currency == "USD"
            )
            if exact and not order_cancelled:
                return Outcome.APPLY_PAID
            return Outcome.LATE_CAPTURE_AND_FAIL
        return Outcome.NOOP if already_late_captured else Outcome.LATE_CAPTURE
    if payment_status not in LIVE:
        return Outcome.NOOP
    if result.state == "processing":
        return Outcome.MARK_PROCESSING if payment_status is PaymentStatus.PENDING else Outcome.NOOP
    if result.state == "failed":
        return Outcome.MARK_FAILED
    if result.state == "expired":
        return Outcome.MARK_EXPIRED
    return Outcome.NOOP
