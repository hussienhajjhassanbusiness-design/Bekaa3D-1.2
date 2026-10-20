"""The mock provider against Redis (VS-023 plan 3.6). Only `simulate` changes its state;
VS-023's contract suite (step 14) runs the full matrix over every adapter."""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.payments.application.ports import CreatePayment, PaymentRef
from app.payments.domain.exceptions import InvalidSignatureError, MalformedEventError
from app.payments.domain.outcome import ProviderResult
from app.payments.infrastructure.providers.mock import MockPaymentProvider, sign

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
SECRET = "test-secret"


@pytest_asyncio.fixture
async def mock() -> AsyncIterator[MockPaymentProvider]:
    provider = MockPaymentProvider(
        redis_url=get_settings().redis_url,
        webhook_secret=SECRET,
        frontend_base_url="http://shop.test/",
    )
    yield provider
    await provider.aclose()


async def _create(mock: MockPaymentProvider, amount: int = 1500) -> uuid.UUID:
    payment_id = uuid.uuid4()
    await mock.create_payment(CreatePayment(payment_id, "B3D-ABCD1234", amount, "USD", ""))
    return payment_id


async def test_create_answers_pending_by_merchant_reference_alone(
    mock: MockPaymentProvider,
) -> None:
    payment_id = uuid.uuid4()
    created = await mock.create_payment(CreatePayment(payment_id, "B3D-ABCD1234", 1500, "USD", ""))
    assert created.provider_payment_id.startswith("mock_")
    assert created.redirect_url == "http://shop.test/checkout/return?order=B3D-ABCD1234"
    status = await mock.query_status(PaymentRef(payment_id, None))
    assert status.result == ProviderResult("pending", None, None)
    assert status.provider_payment_id == created.provider_payment_id


@pytest.mark.parametrize(
    ("captured", "expected"),
    [(None, 1500), (1000, 1000), (2000, 2000)],
    ids=["full", "under", "over"],
)
async def test_simulate_paid_captures_the_amount_it_is_told(
    mock: MockPaymentProvider, captured: int | None, expected: int
) -> None:
    payment_id = await _create(mock)
    await mock.simulate(payment_id, "paid", captured)
    status = await mock.query_status(PaymentRef(payment_id, None))
    assert status.result == ProviderResult("paid", expected, "USD")


@pytest.mark.parametrize("state", ["processing", "failed", "expired"])
async def test_simulate_other_states_capture_nothing(mock: MockPaymentProvider, state: str) -> None:
    payment_id = await _create(mock)
    await mock.simulate(payment_id, state)  # type: ignore[arg-type]
    assert (await mock.query_status(PaymentRef(payment_id, None))).result == ProviderResult(
        state,  # type: ignore[arg-type]
        None,
        None,
    )


async def test_a_payment_the_mock_never_created_is_unknown_and_cannot_be_simulated(
    mock: MockPaymentProvider,
) -> None:
    status = await mock.query_status(PaymentRef(uuid.uuid4(), None))
    assert status.result == ProviderResult("unknown", None, None)
    assert status.provider_payment_id is None
    with pytest.raises(LookupError):
        await mock.simulate(uuid.uuid4(), "paid")


async def test_unknown_can_never_be_stored(mock: MockPaymentProvider) -> None:
    payment_id = await _create(mock)
    with pytest.raises(ValueError, match="cannot be simulated"):
        await mock.simulate(payment_id, "unknown")
    assert (await mock.query_status(PaymentRef(payment_id, None))).result.state == "pending"


def test_parse_webhook_checks_the_signature_before_reading(mock: MockPaymentProvider) -> None:
    reference = uuid.uuid4()
    body = json.dumps(
        {"event_id": "ev_1", "type": "payment.updated", "payment_reference": str(reference)}
    ).encode()
    event = mock.parse_webhook({"X-Mock-Signature": sign(SECRET, body)}, body)
    assert (event.event_id, event.event_type, event.payment_reference) == (
        "ev_1",
        "payment.updated",
        reference,
    )
    with pytest.raises(InvalidSignatureError):
        mock.parse_webhook({"X-Mock-Signature": sign("other", body)}, body)
    with pytest.raises(InvalidSignatureError):
        mock.parse_webhook({}, body)
    with pytest.raises(MalformedEventError):
        mock.parse_webhook({"x-mock-signature": sign(SECRET, b"[]")}, b"[]")
