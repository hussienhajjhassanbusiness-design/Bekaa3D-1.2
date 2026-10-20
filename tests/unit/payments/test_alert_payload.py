"""The alert payload (VS-024 plan 3.5; 2.1): the kind, the ids and what an admin needs to
act, never a redirect URL, provider reference or customer contact."""

import uuid

from app.payments.domain.alerts import DETAIL_KEYS, AlertKind, alert_payload

PAYMENT, ORDER = uuid.uuid4(), uuid.uuid4()


def test_only_the_allowed_details_survive() -> None:
    payload = alert_payload(
        AlertKind.LATE_CAPTURE,
        payment_id=PAYMENT,
        order_id=ORDER,
        details={
            "order_number": "B3D-1",
            "reason": "amount_mismatch",
            "captured_amount_cents": 900,
            "captured_currency": "USD",
            "expected_amount_cents": 1000,
            "redirect_url": "https://pay.example/s",
            "provider_payment_id": "mock_abc",
            "customer_email": "a@example.com",
            "provider_metadata": {"redirect_url": "https://pay.example/s"},
        },
    )
    assert payload == {
        "event": "payment.alert.late_capture",
        "kind": "late_capture",
        "payment_id": str(PAYMENT),
        "order_id": str(ORDER),
        "order_number": "B3D-1",
        "reason": "amount_mismatch",
        "captured_amount_cents": 900,
        "captured_currency": "USD",
        "expected_amount_cents": 1000,
    }


def test_no_reference_url_or_contact_key_is_allowed() -> None:
    for key in DETAIL_KEYS:
        assert not any(word in key for word in ("url", "reference", "email", "metadata"))
    assert "provider_payment_id" not in DETAIL_KEYS


def test_a_provider_alert_has_no_ids() -> None:
    payload = alert_payload(
        AlertKind.PROVIDER_UNREACHABLE, payment_id=None, order_id=None, details={"provider": "x"}
    )
    assert (payload["payment_id"], payload["order_id"], payload["provider"]) == (None, None, "x")
