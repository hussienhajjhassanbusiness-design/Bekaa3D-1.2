"""A crash between checkout's two transactions (VS-023 plan 3.7, 6.2). The claim stays
`in_progress` naming the order, so a retry can never place a second order or make a
second provider call; the payment is recovered by merchant reference (VS-024)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.core.config import get_settings
from app.main import app as main_app
from app.payments.application.ports import PaymentRef
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for
from tests.integration.ordering.checkout_support import (
    Rows,
    buyer,
    new_key,
    post_checkout,
    rows,
    shop_open,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]


def _spy(calls: list[Any]) -> None:
    """Counts `create_payment` on this lifespan's own mock instance."""
    provider = main_app.state.payment_providers["mock"]
    create = provider.create_payment

    async def spy(request: Any) -> Any:
        calls.append(request)
        return await create(request)

    provider.create_payment = spy


async def _state(engine: AsyncEngine, user_id: uuid.UUID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT o.id AS order_id, o.order_number, o.status, p.id AS payment_id,"
                    " p.status AS payment_status, p.provider_payment_id, i.state,"
                    " i.resource_id, i.status_code, i.response_body"
                    " FROM orders o JOIN payments p ON p.order_id = o.id"
                    " JOIN idempotency_records i ON i.user_id = o.user_id WHERE o.user_id = :u"
                ),
                {"u": user_id},
            )
        ).one()


async def _stl(db: AsyncSession) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db), type=ProductType.STL)).id


async def test_a_crash_before_the_provider_call_leaves_one_order_and_no_payment_started(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[Any] = []

    async def crash(provider: Any, request: Any) -> Any:
        raise RuntimeError("process killed before the provider call")

    monkeypatch.setattr("app.ordering.api.checkout.start_online_payment", crash)
    key = new_key()
    stl = await _stl(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        user = await buyer(client, db_session, stl)
        _spy(provider_calls)
        crashed = post_checkout(client, key=key)
        after_crash = await _state(db_engine, user.id)
        retried = post_checkout(client, key=key)

    assert_problem(crashed, 500, "INTERNAL_ERROR")
    assert provider_calls == []
    assert (after_crash.status, after_crash.payment_status) == ("pending_payment", "pending")
    assert after_crash.provider_payment_id is None
    assert (after_crash.state, after_crash.resource_id) == ("in_progress", after_crash.order_id)
    assert after_crash.status_code is None and after_crash.response_body is None

    assert_problem(retried, 409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
    assert retried.headers["Retry-After"] == "2"
    assert (retried.json()["order_id"], retried.json()["order_number"]) == (
        str(after_crash.order_id),
        after_crash.order_number,
    )
    assert provider_calls == []
    assert await _state(db_engine, user.id) == after_crash
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)


async def test_a_crash_after_the_provider_call_never_calls_it_again(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[Any] = []

    async def crash(self: Any, record_id: Any, **kwargs: Any) -> None:
        raise RuntimeError("process killed in Tx2, after the provider answered")

    monkeypatch.setattr(SqlIdempotencyStore, "complete", crash)
    key = new_key()
    stl = await _stl(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        user = await buyer(client, db_session, stl)
        _spy(provider_calls)
        crashed = post_checkout(client, key=key)
        after_crash = await _state(db_engine, user.id)
        retried = post_checkout(client, key=key)
    # A separate instance on the same Redis: what VS-024's reconciliation would query.
    mock = MockPaymentProvider(
        redis_url=get_settings().redis_url, webhook_secret="unused", frontend_base_url=""
    )
    try:
        recovered = await mock.query_status(PaymentRef(after_crash.payment_id, None))
    finally:
        await mock.aclose()

    assert_problem(crashed, 500, "INTERNAL_ERROR")
    assert len(provider_calls) == 1
    assert provider_calls[0].payment_id == after_crash.payment_id
    assert after_crash.provider_payment_id is None, "Tx2 rolled back with the crash"
    assert (after_crash.state, after_crash.resource_id) == ("in_progress", after_crash.order_id)

    assert_problem(retried, 409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
    assert retried.json()["order_id"] == str(after_crash.order_id)
    assert len(provider_calls) == 1
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)

    assert recovered.result.state == "pending"
    assert recovered.provider_payment_id is not None
    assert recovered.provider_payment_id.startswith("mock_")
