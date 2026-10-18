"""VS-023 checkout races 1-4 (plan 6.3, 8.1), through the real route on one running app.
Each racer is released at a barrier inside the transaction, so the requests overlap."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.ordering.application.services import cart as cart_service
from app.ordering.application.services import checkout as checkout_service
from app.ordering.infrastructure.orders import SqlOrderStore
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    ITEMS,
    checkout_body,
    new_key,
    rows,
    shop_open,  # noqa: F401
)
from tests.integration.payments.support import NOW

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
HOLD_SECONDS = 0.2


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI]) -> AsyncIterator[FastAPI]:
    async with running_app(make_app) as running:
        yield running


async def _buyer(
    app: FastAPI, db: AsyncSession, *products: uuid.UUID
) -> tuple[httpx.AsyncClient, uuid.UUID]:
    user = await create_user(db)
    client = async_client(app)
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    for product_id in products:
        added = await client.post(
            ITEMS, json={"product_id": str(product_id)}, headers=_csrf(client)
        )
        assert added.status_code == 200, added.text
    return client, user.id


def _csrf(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


async def _checkout(
    client: httpx.AsyncClient, key: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    return await client.post(
        CHECKOUT,
        json=body or checkout_body(),
        headers=_csrf(client) | {"Idempotency-Key": key},
    )


def _spy_provider(app: FastAPI) -> list[Any]:
    calls: list[Any] = []
    provider = app.state.payment_providers["mock"]
    create = provider.create_payment

    async def spy(request: Any) -> Any:
        calls.append(request)
        return await create(request)

    provider.create_payment = spy
    return calls


async def _stl(db: AsyncSession) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db), type=ProductType.STL)).id


async def test_race_1_two_keys_one_cart_place_one_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)
    original = cart_service.lock_cart_for_checkout

    async def synced(*args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        locked = await original(*args, **kwargs)
        await asyncio.sleep(HOLD_SECONDS)
        return locked

    monkeypatch.setattr(checkout_service, "lock_cart_for_checkout", synced)
    client, user_id = await _buyer(app, db_session, await _stl(db_session))
    try:
        responses = await asyncio.gather(_checkout(client, new_key()), _checkout(client, new_key()))
    finally:
        await client.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], [r.text for r in responses]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["code"] == "CART_EMPTY"
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 1, 1, 0)


async def test_race_2_one_key_one_body_one_order_and_one_provider_call(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)
    original = SqlIdempotencyStore.claim

    async def synced(self: SqlIdempotencyStore, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await original(self, **kwargs)

    monkeypatch.setattr(SqlIdempotencyStore, "claim", synced)
    calls = _spy_provider(app)
    client, user_id = await _buyer(app, db_session, await _stl(db_session))
    key = new_key()
    try:
        responses = await asyncio.gather(_checkout(client, key), _checkout(client, key))
    finally:
        await client.aclose()
    by_status = sorted((r.status_code, r.json().get("code")) for r in responses)
    assert by_status[0] == (201, None), [r.text for r in responses]
    assert by_status[1] in {(201, None), (409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")}
    assert len(calls) == 1
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims) == (1, 1, 1)


async def test_race_3_one_key_two_bodies_one_order_and_one_conflict(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)
    original = SqlIdempotencyStore.claim

    async def synced(self: SqlIdempotencyStore, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await original(self, **kwargs)

    monkeypatch.setattr(SqlIdempotencyStore, "claim", synced)
    client, user_id = await _buyer(app, db_session, await _stl(db_session))
    key = new_key()
    try:
        responses = await asyncio.gather(
            _checkout(client, key, checkout_body(customer_note="first")),
            _checkout(client, key, checkout_body(customer_note="second")),
        )
    finally:
        await client.aclose()
    by_status = sorted((r.status_code, r.json().get("code")) for r in responses)
    assert by_status == [(201, None), (409, "IDEMPOTENCY_KEY_CONFLICT")], [
        r.text for r in responses
    ]
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims) == (1, 1, 1)


async def test_race_4_the_ownership_index_lets_one_live_line_win(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checkout against a second writer of a `pending` line that takes no cart lock (a
    stand-in for VS-041's offer checkout); the writer commits first, checkout gets 409."""
    barrier = asyncio.Barrier(2)
    original = SqlOrderStore.insert_lines

    async def synced(self: SqlOrderStore, *args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        await asyncio.sleep(HOLD_SECONDS / 4)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(SqlOrderStore, "insert_lines", synced)
    stl = await _stl(db_session)
    client, user_id = await _buyer(app, db_session, stl)

    async def other_writer() -> None:
        order_id = uuid.uuid4()
        async with db_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO orders (id, order_number, user_id, customer_email_snapshot,"
                    " source, status, payment_method, subtotal_cents, total_cents,"
                    " terms_accepted_at, digital_terms_accepted_at, digital_terms_version,"
                    " placed_at) VALUES (:id, :n, :u, 'x@example.com', 'cart',"
                    " 'pending_payment', 'online', 1000, 1000, :t, :t, '2026-10-17', :t)"
                ),
                {
                    "id": order_id,
                    "n": f"B3D-{uuid.uuid4().hex[:8].upper()}",
                    "u": user_id,
                    "t": NOW,
                },
            )
            await meet_or_fail(barrier)
            await conn.execute(
                text(
                    "INSERT INTO order_items (order_id, user_id, payment_method, product_id,"
                    " product_type, product_name_snapshot, unit_price_cents, quantity,"
                    " line_total_cents, fulfillment_status) VALUES (:o, :u, 'online', :p,"
                    " 'stl', 'Offer STL', 1000, 1, 1000, 'pending')"
                ),
                {"o": order_id, "u": user_id, "p": stl},
            )
            await asyncio.sleep(HOLD_SECONDS)

    try:
        response, _ = await asyncio.gather(_checkout(client, new_key()), other_writer())
    finally:
        await client.aclose()
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "PRODUCT_ALREADY_OWNED"
    async with db_engine.connect() as conn:
        live = await conn.scalar(
            text(
                "SELECT count(*) FROM order_items WHERE user_id = :u AND product_id = :p"
                " AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')"
            ),
            {"u": user_id, "p": stl},
        )
    assert live == 1
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 0, 0, 1)
