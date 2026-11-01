"""Every API payment adapter keeps the same contract (VS-023 plan 6.4). Parametrised over
`ADAPTERS` but `manual`, which asks and signs nothing (ADR-049) and has its own contract below;
VS-032 adds its sandbox adapter here and gets the whole suite."""

import json
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio

from app.core.config import Settings, get_settings
from app.payments.application.ports import CreatePayment, PaymentProviderPort, PaymentRef
from app.payments.domain.exceptions import (
    InvalidSignatureError,
    MalformedEventError,
    ProviderUnavailableError,
)
from app.payments.domain.outcome import ProviderResult
from app.payments.infrastructure.providers.factory import ADAPTERS
from app.payments.infrastructure.providers.mock import MockPaymentProvider, sign

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
SECRET = "contract-secret"


def _settings(**over: Any) -> Settings:
    return get_settings().model_copy(update={"mock_webhook_secret": SECRET, **over})


async def _drive(
    adapter: PaymentProviderPort, payment_id: uuid.UUID, state: str, **kw: Any
) -> None:
    """What the sandbox would do when the customer pays; the mock's `simulate`."""
    assert isinstance(adapter, MockPaymentProvider), "add the new adapter's driver here"
    await adapter.simulate(payment_id, state, **kw)  # type: ignore[arg-type]


def _signed_event(
    adapter: PaymentProviderPort, payload: dict[str, Any]
) -> tuple[dict[str, str], bytes]:
    body = json.dumps(payload).encode()
    assert isinstance(adapter, MockPaymentProvider)
    return {"X-Mock-Signature": sign(SECRET, body)}, body


@pytest_asyncio.fixture(params=sorted(set(ADAPTERS) - {"manual"}))
async def adapter(request: pytest.FixtureRequest) -> AsyncIterator[PaymentProviderPort]:
    build: Callable[[Settings], PaymentProviderPort] = ADAPTERS[request.param]
    instance = build(_settings())
    yield instance
    await instance.aclose()


async def _created(adapter: PaymentProviderPort, amount: int = 1000) -> uuid.UUID:
    payment_id = uuid.uuid4()
    created = await adapter.create_payment(
        CreatePayment(payment_id, "B3D-CONTRACT", amount, "USD", "http://shop.test/return")
    )
    assert created.provider_payment_id
    return payment_id


async def test_create_then_query_by_merchant_reference_alone(adapter: PaymentProviderPort) -> None:
    payment_id = await _created(adapter)
    status = await adapter.query_status(PaymentRef(payment_id, None))
    assert status.result.state == "pending"
    assert status.provider_payment_id is not None


@pytest.mark.parametrize(
    ("state", "kw", "expected"),
    [
        ("paid", {}, ProviderResult("paid", 1000, "USD")),
        ("paid", {"captured_amount_cents": 900}, ProviderResult("paid", 900, "USD")),
        ("paid", {"captured_amount_cents": 1100}, ProviderResult("paid", 1100, "USD")),
        ("failed", {}, ProviderResult("failed", None, None)),
        ("expired", {}, ProviderResult("expired", None, None)),
        ("processing", {}, ProviderResult("processing", None, None)),
    ],
    ids=["paid", "underpaid", "overpaid", "failed", "expired", "processing"],
)
async def test_query_reports_each_state(
    adapter: PaymentProviderPort, state: str, kw: dict[str, Any], expected: ProviderResult
) -> None:
    payment_id = await _created(adapter)
    await _drive(adapter, payment_id, state, **kw)
    assert (await adapter.query_status(PaymentRef(payment_id, None))).result == expected


async def test_a_reference_the_provider_never_saw_is_unknown(
    adapter: PaymentProviderPort,
) -> None:
    """VS-024 3.2a: "no record" is `unknown`, never `pending`, and carries no capture."""
    status = await adapter.query_status(PaymentRef(uuid.uuid4(), None))
    assert status.result == ProviderResult("unknown", None, None)
    assert status.provider_payment_id is None


@pytest.mark.parametrize("kw", [{}, {"currency": "EUR"}], ids=["default", "foreign"])
async def test_a_capture_names_its_currency_in_upper_case_iso_4217(
    adapter: PaymentProviderPort, kw: dict[str, Any]
) -> None:
    """`ck_payments_captured_shape` refuses anything else, rolling back Tx B (VS-024 3.4)."""
    payment_id = await _created(adapter)
    await _drive(adapter, payment_id, "paid", **kw)
    currency = (await adapter.query_status(PaymentRef(payment_id, None))).result.currency
    assert currency is not None and re.fullmatch(r"[A-Z]{3}", currency), currency


async def test_a_late_success_after_expiry_reports_paid(adapter: PaymentProviderPort) -> None:
    payment_id = await _created(adapter)
    await _drive(adapter, payment_id, "expired")
    await _drive(adapter, payment_id, "paid")
    assert (await adapter.query_status(PaymentRef(payment_id, None))).result.state == "paid"


async def test_an_unreachable_provider_raises_unavailable(adapter: PaymentProviderPort) -> None:
    down = ADAPTERS[adapter.name](_settings(redis_url="redis://127.0.0.1:1/0"))
    try:
        with pytest.raises(ProviderUnavailableError):
            await down.query_status(PaymentRef(uuid.uuid4(), None))
        with pytest.raises(ProviderUnavailableError):
            await down.create_payment(CreatePayment(uuid.uuid4(), "B3D-X", 1000, "USD", ""))
    finally:
        await down.aclose()


def test_a_bad_signature_raises_before_the_body_is_read(adapter: PaymentProviderPort) -> None:
    headers, body = _signed_event(adapter, {"event_id": "ev_1", "type": "payment"})
    with pytest.raises(InvalidSignatureError):
        adapter.parse_webhook(dict.fromkeys(headers, "0" * 64), body)
    with pytest.raises(InvalidSignatureError):
        adapter.parse_webhook({}, b"not even json")


def test_a_duplicate_event_parses_identically(adapter: PaymentProviderPort) -> None:
    reference = str(uuid.uuid4())
    headers, body = _signed_event(
        adapter, {"event_id": "ev_dup", "type": "payment", "payment_reference": reference}
    )
    first, second = adapter.parse_webhook(headers, body), adapter.parse_webhook(headers, body)
    assert first == second
    assert (first.event_id, str(first.payment_reference)) == ("ev_dup", reference)


def test_a_signed_but_unreadable_event_is_malformed(adapter: PaymentProviderPort) -> None:
    headers, body = _signed_event(adapter, {"type": "payment"})
    with pytest.raises(MalformedEventError):
        adapter.parse_webhook(headers, body)


def test_the_adapter_answers_status_queries(adapter: PaymentProviderPort) -> None:
    """Verification relies on asking the provider; an adapter that cannot is refused."""
    assert adapter.supports_status_query is True


# --- `manual` (VS-050, ADR-049): nothing to create, ask or receive -------------------------


async def test_the_manual_adapter_creates_nothing_and_takes_no_webhooks() -> None:
    manual = ADAPTERS["manual"](_settings())
    created = await manual.create_payment(
        CreatePayment(uuid.uuid4(), "B3D-CONTRACT", 1000, "USD", "http://shop.test/return")
    )
    assert (created.provider_payment_id, created.redirect_url) == (None, None)
    assert manual.supports_status_query is False
    assert getattr(manual, "accepts_webhooks", True) is False
    with pytest.raises(InvalidSignatureError):
        manual.parse_webhook({}, b"{}")
    await manual.aclose()
