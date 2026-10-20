"""VS-023 security suite (plan 6.5, moved to Checkpoint 5): forged and replayed webhooks,
body caps, flooding, no HTTP route that can pay a mock payment, `mock_pay.py`'s refusals,
log redaction, and no payment secrets in any error body."""

import importlib.util
import io
import json
import logging
import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest
import structlog
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.main import app as main_app
from app.payments.application.ports import PaymentRef
from app.payments.infrastructure.providers.factory import DEFAULT_MOCK_SECRET
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import client_for, create_user, csrf, login
from tests.integration.ordering.checkout_support import (
    buyer,
    post_checkout,
    shop_open,  # noqa: F401
)
from tests.integration.payments.verification_support import (
    WEBHOOK,
    event_body,
    mock_fixture,  # noqa: F401
    paid_once,
    paid_state,
    pending_payment,
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "app"


# ------------------------------------------------- forged and replayed webhooks


async def test_a_forged_signature_is_refused_and_never_stored(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded)
    tampered = body.replace(b'"payment"', b'"payment.paid"')
    with client_for(main_app) as client:
        wrong_key = client.post(WEBHOOK, content=body, headers=signed(body, "attacker"))
        reused_signature = client.post(WEBHOOK, content=tampered, headers=signed(body))
        no_signature = client.post(WEBHOOK, content=body)
    assert [r.status_code for r in (wrong_key, reused_signature, no_signature)] == [401] * 3
    assert (await paid_state(db_engine, seeded)).payment_status == "pending"


async def test_a_replayed_signed_event_is_applied_once(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded)
    with client_for(main_app) as client:
        replies = [client.post(WEBHOOK, content=body, headers=signed(body)) for _ in range(5)]
    assert {r.status_code for r in replies} == {200}
    assert paid_once(await paid_state(db_engine, seeded))


async def test_a_validly_signed_lie_changes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Someone holding the secret still cannot pay: the provider's own answer decides."""
    seeded = await pending_payment(db_session, mock)
    payload = json.loads(event_body(seeded)) | {"status": "paid", "amount_cents": 1000}
    body = json.dumps(payload).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    assert (await paid_state(db_engine, seeded)).payment_status == "pending"


# -------------------------------------------------------------- body caps


def test_oversized_and_chunked_bodies_are_refused_before_the_signature() -> None:
    big = b"{" + b" " * (64 * 1024) + b"}"

    def chunks() -> Iterator[bytes]:
        for _ in range(10):
            yield b" " * 8192

    with client_for(main_app) as client:
        declared = client.post(WEBHOOK, content=big, headers={"X-Mock-Signature": "x"})
        streamed = client.post(WEBHOOK, content=chunks(), headers={"X-Mock-Signature": "x"})
    assert [declared.status_code, streamed.status_code] == [400, 400]


# ------------------------------------------------------------------ flooding


async def test_flooding_forged_traffic_never_reaches_the_valid_bucket(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    forged = b'{"event_id": "ev_flood", "type": "x"}'
    body = event_body(seeded)
    with client_for(make_app(), ip="10.66.0.1") as attacker:
        codes = [
            attacker.post(WEBHOOK, content=forged, headers=signed(forged, "guess")).status_code
            for _ in range(40)
        ]
        honest = attacker.post(WEBHOOK, content=body, headers=signed(body))
    assert codes.count(429) == 10 and set(codes) == {401, 429}
    assert honest.status_code == 200
    assert paid_once(await paid_state(db_engine, seeded))


# ------------------------------------------- no HTTP route pays a mock payment


def test_no_application_code_can_change_mock_state() -> None:
    """`simulate` is called nowhere in `src`; only tests and `scripts/mock_pay.py`."""
    callers = [
        str(path.relative_to(ROOT))
        for path in SRC.rglob("*.py")
        if re.search(r"\.simulate\(", path.read_text(encoding="utf-8"))
    ]
    assert callers == []


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}/]+(?::path)?\}", str(uuid.uuid4()), path)


async def test_no_route_reached_by_anyone_marks_a_mock_payment_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Every route and method, anonymous and as a verified customer, with an empty body
    and with one naming the payment: the mock still says pending, nothing is paid."""
    seeded = await pending_payment(db_session, mock)
    routes = sorted(
        {
            (method, ctx.path)
            for ctx in iter_route_contexts(main_app.router.routes)
            for method in (ctx.methods or set())
            if ctx.path and method not in {"HEAD", "OPTIONS"}
        }
    )
    assert len(routes) > 60, routes
    customer = await create_user(db_session)
    probe = {"payment_id": str(seeded.payment_id), "status": "paid", "state": "paid"}
    # One client at a time: each runs its own lifespan and loop, and two open together
    # share app.state's Redis and engine across loops (the flake fixed here).
    for as_customer in (False, True):
        with client_for(main_app, raise_server_exceptions=False) as client:
            headers: dict[str, str] = {}
            if as_customer:
                login(client, customer.email)
                headers = csrf(client)
            for method, path in routes:
                for body in (None, probe):
                    client.request(method, _concrete(path), json=body, headers=headers)
    status = await mock.query_status(PaymentRef(seeded.payment_id, None))
    assert status.result.state == "pending"
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.verified_audits) == ("pending", 0)


# ------------------------------------------------------------ mock_pay.py


@pytest.fixture
def mock_pay() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mock_pay", ROOT / "scripts" / "mock_pay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(environment: str, secret: str, provider: str = "mock") -> Settings:
    return get_settings().model_copy(
        update={
            "environment": environment,
            "mock_webhook_secret": secret,
            "payment_provider": provider,
        }
    )


@pytest.mark.parametrize(
    ("environment", "secret"),
    [
        ("production", "own-secret"),
        ("production", DEFAULT_MOCK_SECRET),
        ("staging", DEFAULT_MOCK_SECRET),
        ("Production", "own-secret"),
        ("prod", DEFAULT_MOCK_SECRET),
    ],
)
async def test_mock_pay_refuses_production_and_the_default_secret_outside_dev(
    mock_pay: ModuleType, environment: str, secret: str
) -> None:
    with pytest.raises(SystemExit, match="refuses to run"):
        await mock_pay.run(uuid.uuid4(), "paid", settings=_settings(environment, secret))


async def test_mock_pay_refuses_when_the_mock_is_not_configured(mock_pay: ModuleType) -> None:
    with pytest.raises(SystemExit, match="not mock"):
        await mock_pay.run(uuid.uuid4(), "paid", settings=_settings("development", "s", "none"))


async def test_mock_pay_pays_in_development(
    mock_pay: ModuleType, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    settings = _settings("development", get_settings().mock_webhook_secret)
    assert await mock_pay.run(seeded.payment_id, "paid", settings=settings) is None
    assert (await mock.query_status(PaymentRef(seeded.payment_id, None))).result.state == "paid"


# ------------------------------------------------------------- redaction


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    return buffer


async def test_secrets_signatures_and_payloads_never_reach_the_logs(
    captured_logs: io.StringIO, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock, total_cents=1000)
    marker = f"PAYLOAD-MARKER-{uuid.uuid4().hex}"
    forged = json.dumps({"event_id": "ev_log", "type": "x", "note": marker}).encode()
    ignored = json.dumps(
        {
            "event_id": f"ev_{uuid.uuid4().hex}",
            "type": "x",
            "payment_reference": str(uuid.uuid4()),
            "note": marker,
        }
    ).encode()
    await mock.simulate(seeded.payment_id, "paid", 900)  # a late capture: logged as an error
    late = json.loads(event_body(seeded)) | {"note": marker}
    late_body = json.dumps(late).encode()
    secret = get_settings().mock_webhook_secret
    with client_for(main_app) as client:
        client.post(WEBHOOK, content=forged, headers=signed(forged, "guess"))
        client.post(WEBHOOK, content=ignored, headers=signed(ignored))
        client.post(WEBHOOK, content=late_body, headers=signed(late_body))
    # A careless future log line naming the signing material is redacted too.
    await structlog.get_logger().aerror(
        "probe", signature=signed(late_body)["X-Mock-Signature"], mock_webhook_secret=secret
    )
    logs = captured_logs.getvalue()
    assert "payment_webhook_bad_signature" in logs and "payment_late_capture" in logs
    assert marker not in logs
    assert secret not in logs
    assert signed(late_body)["X-Mock-Signature"] not in logs
    assert signed(forged, "guess")["X-Mock-Signature"] not in logs


# ------------------------------------------------ no payment data in errors


async def test_error_bodies_carry_no_provider_reference_secret_or_signature(
    db_session: AsyncSession, mock: MockPaymentProvider, db_engine: AsyncEngine
) -> None:
    seeded = await pending_payment(db_session, mock)
    body = event_body(seeded)
    forbidden = [
        seeded.reference,
        get_settings().mock_webhook_secret,
        signed(body)["X-Mock-Signature"],
    ]
    with client_for(main_app) as client:
        errors = [
            client.post(WEBHOOK, content=body, headers=signed(body, "guess")),
            client.post(WEBHOOK, content=b"{" + b" " * 70_000 + b"}"),
            client.post(WEBHOOK, content=b'{"type": 1}', headers=signed(b'{"type": 1}')),
        ]
    for response in errors:
        assert response.status_code >= 400
        assert not any(value in response.text for value in forbidden), response.text


@pytest.mark.usefixtures("shop_open")
async def test_checkout_responses_never_expose_provider_references(
    db_session: AsyncSession,
) -> None:
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    with client_for(main_app) as client:
        await buyer(client, db_session, stl)
        response = post_checkout(client)
    assert response.status_code == 201
    text = response.text
    for key in ("provider_payment_id", "provider_metadata", "admin_note", "mock_"):
        assert key not in text, key
