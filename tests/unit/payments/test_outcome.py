"""The payment decision table, row by row (VS-023 plan 3.6, 6.1)."""

import pytest

from app.payments.domain.enums import PaymentStatus
from app.payments.domain.outcome import Outcome, ProviderResult, ProviderState, decide

P = PaymentStatus


def result(
    state: ProviderState, amount: int | None = 1000, currency: str | None = "USD"
) -> ProviderResult:
    return ProviderResult(state=state, captured_amount_cents=amount, currency=currency)


def run(
    status: PaymentStatus,
    res: ProviderResult,
    *,
    cancelled: bool = False,
    late: bool = False,
    payment_amount: int = 1000,
    order_total: int = 1000,
) -> Outcome:
    return decide(
        payment_status=status,
        payment_amount_cents=payment_amount,
        order_total_cents=order_total,
        order_cancelled=cancelled,
        already_late_captured=late,
        result=res,
    )


@pytest.mark.parametrize("status", [P.PAID, P.PARTIALLY_REFUNDED, P.REFUNDED])
def test_a_duplicate_success_is_a_noop(status: PaymentStatus) -> None:
    assert run(status, result("paid")) is Outcome.NOOP
    assert run(status, result("paid"), cancelled=True) is Outcome.NOOP


@pytest.mark.parametrize("status", [P.PENDING, P.PROCESSING])
def test_an_exact_capture_on_a_live_attempt_is_applied(status: PaymentStatus) -> None:
    assert run(status, result("paid")) is Outcome.APPLY_PAID


@pytest.mark.parametrize(
    ("res", "payment_amount", "order_total"),
    [
        (result("paid", 999), 1000, 1000),  # underpayment
        (result("paid", 1001), 1000, 1000),  # overpayment
        (result("paid", 1000, "EUR"), 1000, 1000),  # wrong currency
        (result("paid", None), 1000, 1000),  # no captured amount reported
        (result("paid", 1000, None), 1000, 1000),  # no currency reported
        (result("paid", 1000), 1000, 1200),  # attempt amount no longer the order total
    ],
    ids=["under", "over", "currency", "no-amount", "no-currency", "stale-attempt"],
)
def test_a_mismatched_capture_is_never_applied(
    res: ProviderResult, payment_amount: int, order_total: int
) -> None:
    got = run(P.PENDING, res, payment_amount=payment_amount, order_total=order_total)
    assert got is Outcome.LATE_CAPTURE_AND_FAIL


def test_a_capture_on_a_cancelled_order_is_a_late_capture() -> None:
    assert run(P.PENDING, result("paid"), cancelled=True) is Outcome.LATE_CAPTURE_AND_FAIL


@pytest.mark.parametrize("status", [P.FAILED, P.EXPIRED])
def test_a_capture_on_a_dead_attempt_is_a_late_capture_once(status: PaymentStatus) -> None:
    assert run(status, result("paid")) is Outcome.LATE_CAPTURE
    assert run(status, result("paid"), late=True) is Outcome.NOOP


def test_processing_moves_only_a_pending_attempt() -> None:
    assert run(P.PENDING, result("processing")) is Outcome.MARK_PROCESSING
    assert run(P.PROCESSING, result("processing")) is Outcome.NOOP


@pytest.mark.parametrize("status", [P.PENDING, P.PROCESSING])
def test_failure_and_expiry_end_a_live_attempt(status: PaymentStatus) -> None:
    assert run(status, result("failed")) is Outcome.MARK_FAILED
    assert run(status, result("expired")) is Outcome.MARK_EXPIRED


@pytest.mark.parametrize("status", [P.PAID, P.FAILED, P.EXPIRED, P.REFUNDED])
@pytest.mark.parametrize("state", ["pending", "processing", "failed", "expired"])
def test_non_paid_results_never_touch_a_settled_attempt(
    status: PaymentStatus, state: ProviderState
) -> None:
    assert run(status, result(state)) is Outcome.NOOP


def test_a_pending_result_on_a_pending_attempt_changes_nothing() -> None:
    assert run(P.PENDING, result("pending")) is Outcome.NOOP
