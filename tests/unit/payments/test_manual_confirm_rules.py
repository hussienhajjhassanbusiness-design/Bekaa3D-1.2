"""Manual confirm's refusals (VS-024 plan 2.3 steps 1-3, 6.1): cash, a status-capable
provider, and any differing amount or currency, which is never a late capture."""

import pytest

from app.payments.domain.enums import PaymentProvider
from app.payments.domain.manual import (
    CaptureRefusal,
    ConfirmRefusal,
    capture_refusal,
    confirm_refusal,
)
from app.payments.domain.release import Capability


def refuse(
    *,
    provider: PaymentProvider = PaymentProvider.MOCK,
    capability: Capability = Capability.NO_STATUS_QUERY,
    amount: int = 1000,
    currency: str = "USD",
) -> ConfirmRefusal | None:
    return confirm_refusal(
        provider=provider,
        capability=capability,
        payment_amount_cents=1000,
        typed_amount_cents=amount,
        typed_currency=currency,
    )


@pytest.mark.parametrize("capability", list(Capability))
def test_a_cash_payment_is_refused_first(capability: Capability) -> None:
    refusal = refuse(provider=PaymentProvider.CASH, capability=capability, amount=1)
    assert refusal is ConfirmRefusal.CASH_PAYMENT


def test_a_status_capable_provider_is_reconciled_instead() -> None:
    refusal = refuse(capability=Capability.STATUS_QUERY, amount=1)
    assert refusal is ConfirmRefusal.STATUS_QUERY_AVAILABLE


@pytest.mark.parametrize(
    ("amount", "currency"), [(999, "USD"), (1001, "USD"), (0, "USD"), (1000, "EUR")]
)
@pytest.mark.parametrize("capability", [Capability.NO_STATUS_QUERY, Capability.NOT_CONFIGURED])
def test_a_differing_amount_or_currency_is_refused(
    amount: int, currency: str, capability: Capability
) -> None:
    refusal = refuse(capability=capability, amount=amount, currency=currency)
    assert refusal is ConfirmRefusal.AMOUNT_MISMATCH


@pytest.mark.parametrize("capability", [Capability.NO_STATUS_QUERY, Capability.NOT_CONFIGURED])
def test_the_exact_amount_in_usd_is_applied(capability: Capability) -> None:
    assert refuse(capability=capability) is None


# --- Record-capture (VS-030 plan 3.6, Q5): a mismatch only, on an attempt never paid -------

R = CaptureRefusal


def capture(
    *,
    provider: PaymentProvider = PaymentProvider.MOCK,
    capability: Capability = Capability.NO_STATUS_QUERY,
    reached_paid: bool = False,
    late_captured: bool = False,
    amount: int = 1200,
    currency: str = "USD",
) -> CaptureRefusal | None:
    return capture_refusal(
        provider=provider,
        capability=capability,
        reached_paid=reached_paid,
        late_captured=late_captured,
        payment_amount_cents=1000,
        typed_amount_cents=amount,
        typed_currency=currency,
    )


def test_record_capture_refusals_in_order() -> None:
    assert capture() is None
    assert capture(amount=1000, currency="LBP") is None  # the currency differs
    assert capture(provider=PaymentProvider.CASH, capability=Capability.STATUS_QUERY) is (
        R.CASH_PAYMENT
    )
    assert capture(capability=Capability.STATUS_QUERY) is R.STATUS_QUERY_AVAILABLE
    assert capture(reached_paid=True, late_captured=True) is R.ALREADY_PAID
    assert capture(late_captured=True) is R.ALREADY_LATE_CAPTURED
    assert capture(amount=1000) is R.USE_CONFIRM
