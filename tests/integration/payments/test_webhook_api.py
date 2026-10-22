"""`POST /api/v1/webhooks/payments/{provider}` (VS-023 plan 2.2, 6.2): body cap before the
signature, signature before the provider bucket, deduplicated storage, and a 200 that
never changes a payment by itself (verification runs after it)."""

import json
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.payments.infrastructure.providers import factory
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user
from tests.integration.ordering.test_order_payment_schema import (
    Ctx,
    cash_delivery_order,
    cash_payment,
    physical_line,
)
from tests.integration.payments.verification_support import (
    WEBHOOK,
    Seeded,
    event_body,
    mock_fixture,  # noqa: F401
    paid_once,
    paid_state,
    pending_payment,
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _events(engine: AsyncEngine, seeded: Seeded | None = None) -> list[dict[str, object]]:
    sql = (
        "SELECT provider_event_id, payment_id, processed_at IS NOT NULL AS processed,"
        " processing_error, signature_valid FROM webhook_events"
    )
    params: dict[str, object] = {}
    if seeded is not None:
        sql += " WHERE payload->>'payment_reference' = :r OR provider_payment_id = :p"
        params = {"r": str(seeded.payment_id), "p": seeded.reference}
    async with engine.connect() as conn:
        return [dict(row._mapping) for row in await conn.execute(text(sql), params)]


async def _bucket(name: str) -> int | None:
    client = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    try:
        value = await client.get(f"ratelimit:{name}")
    finally:
        await client.aclose()
    return int(value) if value is not None else None


async def test_a_signed_event_is_stored_and_verified_after_the_200(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded)
    with client_for(main_app) as client:
        started = time.perf_counter()
        response = client.post(WEBHOOK, content=body, headers=signed(body))
        elapsed = time.perf_counter() - started
    assert (response.status_code, response.json()) == (200, {"received": True})
    print(f"receipt to paid (200 plus background verification): {elapsed:.3f}s")
    [event] = await _events(db_engine, seeded)
    assert (event["payment_id"], event["processed"], event["signature_valid"]) == (
        seeded.payment_id,
        True,
        True,
    )
    assert paid_once(await paid_state(db_engine, seeded))


async def test_the_webhook_body_is_never_trusted(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """A correctly signed event claiming success changes nothing while the provider
    itself still says pending (a forged or premature callback)."""
    seeded = await pending_payment(db_session, mock)
    payload = json.loads(event_body(seeded)) | {"type": "payment.paid", "status": "paid"}
    body = json.dumps(payload).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.line_status, state.order_status) == (
        "pending",
        "pending",
        "pending_payment",
    )
    assert [e["processed"] for e in await _events(db_engine, seeded)] == [True]


async def test_a_replayed_event_is_stored_once_and_applied_once(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded, event_id=f"ev_{uuid.uuid4().hex}")
    with client_for(main_app) as client:
        statuses = [
            client.post(WEBHOOK, content=body, headers=signed(body)).status_code for _ in range(3)
        ]
    assert statuses == [200, 200, 200]
    assert len(await _events(db_engine, seeded)) == 1
    assert paid_once(await paid_state(db_engine, seeded))


async def test_a_wrong_signature_is_401_stores_nothing_and_spends_only_the_ip_bucket(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded)
    with client_for(main_app, ip="10.9.8.7") as client:
        response = client.post(WEBHOOK, content=body, headers=signed(body, "not-the-secret"))
    assert_problem(response, 401, "WEBHOOK_SIGNATURE_INVALID")
    assert await _events(db_engine, seeded) == []
    assert await _bucket("webhook-unverified:10.9.8.7") == 1
    assert await _bucket("webhook:mock") is None
    assert (await paid_state(db_engine, seeded)).payment_status == "pending"


async def test_an_oversized_body_is_400_before_the_signature_and_spends_no_bucket(
    db_engine: AsyncEngine,
) -> None:
    body = json.dumps({"event_id": "ev_big", "type": "x", "pad": "a" * 70_000}).encode()
    with client_for(main_app, ip="10.9.8.6") as client:
        unsigned = client.post(WEBHOOK, content=body, headers={"X-Mock-Signature": "bad"})
        honest = client.post(WEBHOOK, content=body, headers=signed(body))
    assert_problem(unsigned, 400, "VALIDATION_ERROR")
    assert_problem(honest, 400, "VALIDATION_ERROR")
    assert await _bucket("webhook-unverified:10.9.8.6") is None
    assert await _bucket("webhook:mock") is None
    async with db_engine.connect() as conn:
        assert not await conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE provider_event_id = 'ev_big'")
        )


async def test_a_body_under_the_cap_that_grows_past_it_once_stored_is_400(
    db_engine: AsyncEngine,
) -> None:
    """jsonb::text adds a space after every ':' and ','; the CHECK measures that text."""
    payload = {"event_id": "ev_grows", "type": "x"} | {f"k{i}": 1 for i in range(6200)}
    body = json.dumps(payload, separators=(",", ":")).encode()
    assert len(body) <= 64 * 1024
    with client_for(main_app) as client:
        response = client.post(WEBHOOK, content=body, headers=signed(body))
    assert_problem(response, 400, "VALIDATION_ERROR")
    async with db_engine.connect() as conn:
        assert not await conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE provider_event_id = 'ev_grows'")
        )


async def test_a_chunked_oversized_body_is_refused_without_a_content_length() -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(9):
            yield b"x" * 8192

    with client_for(main_app) as client:
        response = client.post(WEBHOOK, content=chunks(), headers={"X-Mock-Signature": "bad"})
    assert_problem(response, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("provider", ["cash", "unknown", "stripe"])
async def test_an_unconfigured_provider_is_404_and_touches_nothing(
    db_engine: AsyncEngine, provider: str
) -> None:
    body = json.dumps({"event_id": f"ev_{provider}_404", "type": "x"}).encode()
    with client_for(main_app, ip="10.9.8.5") as client:
        response = client.post(
            f"/api/v1/webhooks/payments/{provider}", content=body, headers=signed(body)
        )
    assert response.status_code == 404
    assert await _bucket("webhook-unverified:10.9.8.5") is None
    assert await _bucket(f"webhook:{provider}") is None


async def test_with_no_online_provider_every_webhook_path_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    get_settings.cache_clear()
    body = json.dumps({"event_id": "ev_none", "type": "x"}).encode()
    with client_for(main_app) as client:
        response = client.post(WEBHOOK, content=body, headers=signed(body))
    get_settings.cache_clear()
    assert response.status_code == 404


async def test_an_event_for_an_unknown_payment_is_stored_as_ignored(
    db_engine: AsyncEngine,
) -> None:
    event_id = f"ev_{uuid.uuid4().hex}"
    body = json.dumps(
        {"event_id": event_id, "type": "payment", "payment_reference": str(uuid.uuid4())}
    ).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT payment_id, processed_at IS NOT NULL AS processed, processing_error"
                    " FROM webhook_events WHERE provider_event_id = :e"
                ),
                {"e": event_id},
            )
        ).one()
    assert (row.payment_id, row.processed, row.processing_error) == (None, True, "unknown_payment")


async def test_an_event_whose_reference_contradicts_the_payment_is_ignored(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    payload = json.loads(event_body(seeded)) | {"provider_payment_id": "mock_someone_else"}
    body = json.dumps(payload).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    [event] = await _events(db_engine, seeded)
    assert (event["payment_id"], event["processing_error"]) == (None, "reference_mismatch")
    assert (await paid_state(db_engine, seeded)).payment_status == "pending"


async def _cash_payment(db: AsyncSession) -> uuid.UUID:
    """A paid cash payment: the only `payments.provider` other than `mock` today."""
    refs = await seed_refs(db)
    physical = (await seed_product(db, refs)).id
    c = Ctx(
        (await create_user(db)).id,
        (await create_user(db, role=UserRole.ADMIN)).id,
        physical,
        physical,
    )
    order_id, payment_id = uuid.uuid4(), uuid.uuid4()
    for sql, params in (
        cash_delivery_order(c, order_id),
        physical_line(c, order_id),
        cash_payment(c, order_id, id=payment_id),
    ):
        await db.execute(text(sql), params)
    await db.commit()
    return payment_id


async def test_an_event_naming_another_providers_payment_is_stored_as_provider_mismatch(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """FR-07: stored and ignored, never linked or verified, the payment untouched."""
    payment_id = await _cash_payment(db_session)
    event_id = f"ev_{uuid.uuid4().hex}"
    payload = {"event_id": event_id, "type": "payment", "payment_reference": str(payment_id)}
    body = json.dumps(payload).encode()
    sql = "SELECT status, updated_at, provider_payment_id FROM payments WHERE id = :p"
    async with db_engine.connect() as conn:
        before = (await conn.execute(text(sql), {"p": payment_id})).one()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    async with db_engine.connect() as conn:
        event = (
            await conn.execute(
                text(
                    "SELECT payment_id, processed_at IS NOT NULL AS processed, processing_error"
                    " FROM webhook_events WHERE provider_event_id = :e"
                ),
                {"e": event_id},
            )
        ).one()
        after = (await conn.execute(text(sql), {"p": payment_id})).one()
    assert (event.payment_id, event.processed, event.processing_error) == (
        None,
        True,
        "provider_mismatch",
    )
    assert after == before


class _StubProvider:
    """A test-only online adapter, so production boots without the mock (VS-023 plan)."""

    supports_status_query = False

    async def aclose(self) -> None:
        return None


async def test_in_production_a_webhook_to_the_mock_is_404_and_stores_nothing(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(factory.ADAPTERS, "stub", lambda settings: _StubProvider())
    production = {
        "ENVIRONMENT": "production",
        "PAYMENT_PROVIDER": "stub",
        "CAPTCHA_PROVIDER": "turnstile",
        "TURNSTILE_SECRET": "test-only",
        "PHONE_HASH_SALT": "p" * 64,
    }
    for name, value in production.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    event_id = f"ev_{uuid.uuid4().hex}"
    body = json.dumps({"event_id": event_id, "type": "payment"}).encode()
    try:
        with client_for(main_app, ip="10.9.8.6") as client:
            assert set(main_app.state.payment_providers) == {"stub"}
            response = client.post(WEBHOOK, content=body, headers=signed(body))
    finally:
        get_settings.cache_clear()
    assert response.status_code == 404
    async with db_engine.connect() as conn:
        stored = await conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE provider_event_id = :e"),
            {"e": event_id},
        )
    assert stored == 0
    assert await _bucket("webhook-unverified:10.9.8.6") is None
    assert await _bucket("webhook:mock") is None


async def test_a_signed_unreadable_body_is_400_and_not_stored() -> None:
    body = b'{"type": "payment"}'
    with client_for(main_app) as client:
        response = client.post(WEBHOOK, content=body, headers=signed(body))
    assert_problem(response, 400, "VALIDATION_ERROR")


async def test_flooding_invalid_traffic_does_not_exhaust_the_valid_bucket(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    forged = json.dumps({"event_id": "ev_forged", "type": "x"}).encode()
    body = event_body(seeded)
    with (
        client_for(make_app(), ip="10.7.7.7") as attacker,
        client_for(make_app(), ip="10.7.7.8") as other,
    ):
        flood = [
            attacker.post(WEBHOOK, content=forged, headers=signed(forged, "guess")).status_code
            for _ in range(31)
        ]
        from_attacker_ip = attacker.post(WEBHOOK, content=body, headers=signed(body))
        from_other_ip = other.post(WEBHOOK, content=body, headers=signed(body))
    assert flood[:30] == [401] * 30
    assert flood[30] == 429
    assert from_attacker_ip.status_code == 200, "a signed event is not limited by the IP flood"
    assert from_other_ip.status_code == 200
    assert await _bucket("webhook:mock") == 2
    assert paid_once(await paid_state(db_engine, seeded))


async def test_the_valid_bucket_limits_signed_traffic_per_provider(
    db_engine: AsyncEngine,
) -> None:
    client_redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    try:
        await client_redis.set("ratelimit:webhook:mock", 600, ex=60)
    finally:
        await client_redis.aclose()
    body = json.dumps({"event_id": "ev_601", "type": "x"}).encode()
    with client_for(main_app) as client:
        response = client.post(WEBHOOK, content=body, headers=signed(body))
    assert_problem(response, 429, "RATE_LIMITED")
    async with db_engine.connect() as conn:
        assert not await conn.scalar(
            text("SELECT count(*) FROM webhook_events WHERE provider_event_id = 'ev_601'")
        )


async def test_the_tx2_crash_payment_is_found_by_our_id_and_its_reference_stored(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Revision 5 item 1: the row has no provider id; the event names only our id."""
    seeded = await pending_payment(db_session, mock, store_reference=False)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded, reference=False)
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    state = await paid_state(db_engine, seeded)
    assert paid_once(state)
    assert state.provider_payment_id == seeded.reference


async def test_an_event_naming_only_the_provider_reference_resolves(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    body = event_body(seeded, ours=False)
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    assert paid_once(await paid_state(db_engine, seeded))
