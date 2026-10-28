"""VS-045 races on real PostgreSQL (FR-03 concurrency; ADR-047). As VS-029b's, a held row lock
queues the racers in a chosen order before it is released, so they provably overlap. Never an
anonymised account with a new order, report or address; never a deadlock."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.fulfillment.delivery_support import admin_client
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.identity.deletion_support import ME, one, scalar, wait_for_waiters
from tests.integration.negotiation.offer_support import seed_offer, shop_open, stl  # noqa: F401
from tests.integration.ordering.checkout_support import CHECKOUT, ITEMS, checkout_body, new_key
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    random_phone,
    setting,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
RACE_TIMEOUT_SECONDS = 20
Racer = Callable[[], Coroutine[Any, Any, httpx.Response]]


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI]) -> AsyncIterator[FastAPI]:
    async with running_app(make_app) as running:
        yield running


@asynccontextmanager
async def _held(engine: AsyncEngine, sql: str, **params: Any) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        await conn.execute(text(sql), params)
        try:
            yield conn
        finally:
            await conn.rollback()


async def _queued(
    engine: AsyncEngine, lock_sql: str, racers: list[Racer], **params: Any
) -> list[httpx.Response]:
    """Each racer starts once the previous one waits on a lock; Postgres then grants the held
    lock in queue order. Waits are counted, not matched by SQL text (audit A-06)."""
    async with _held(engine, lock_sql, **params) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            try:
                await wait_for_waiters(engine, n)
            except AssertionError as exc:
                done = [t.result().text for t in tasks if t.done()]
                raise AssertionError(f"{exc}; finished early: {done}") from None
        await held.commit()
    return list(await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS))


async def _client(app: FastAPI, email: str) -> httpx.AsyncClient:
    client = async_client(app)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client


def _headers(client: httpx.AsyncClient, key: bool = False) -> dict[str, str]:
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    return headers | ({"Idempotency-Key": new_key()} if key else {})


def _delete(client: httpx.AsyncClient) -> Racer:
    async def call() -> httpx.Response:
        return await client.request(
            "DELETE", ME, json={"current_password": PASSWORD}, headers=_headers(client)
        )

    return call


def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any], key: bool = False) -> Racer:
    async def call() -> httpx.Response:
        return await client.post(path, json=body, headers=_headers(client, key))

    return call


def _refused(response: httpx.Response, status: int, **fields: str) -> None:
    """Status first, so a wrong outcome (a 201 or 204) fails with its body, not a KeyError."""
    assert response.status_code == status, response.text
    body = response.json()
    assert {k: body.get(k) for k in fields} == fields, body


async def _anonymised(engine: AsyncEngine, user_id: uuid.UUID) -> bool:
    found = await scalar(engine, "SELECT anonymized_at FROM users WHERE id = :u", u=user_id)
    return found is not None


async def _orders(engine: AsyncEngine, user_id: uuid.UUID) -> int:
    return int(await scalar(engine, "SELECT count(*) FROM orders WHERE user_id = :u", u=user_id))


async def _cart_buyer(app: FastAPI, db: AsyncSession) -> tuple[Any, httpx.AsyncClient]:
    user = await create_user(db)
    client = await _client(app, user.email)
    added = await client.post(
        ITEMS, json={"product_id": str(await stl(db))}, headers=_headers(client)
    )
    assert added.status_code == 200, added.text
    return user, client


_CART = "SELECT id FROM carts WHERE user_id = :u FOR UPDATE"


async def test_deletion_first_leaves_a_waiting_cart_checkout_no_account(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user, client = await _cart_buyer(app, db_session)
    try:
        deleted, checkout = await _queued(
            db_engine,
            _CART,
            [_delete(client), _post(client, CHECKOUT, checkout_body(), key=True)],
            u=user.id,
        )
    finally:
        await client.aclose()
    assert deleted.status_code == 204, deleted.text
    _refused(checkout, 401, code="AUTH_REQUIRED")
    assert await _orders(db_engine, user.id) == 0 and await _anonymised(db_engine, user.id)


async def test_checkout_first_makes_a_waiting_deletion_see_the_open_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user, client = await _cart_buyer(app, db_session)
    try:
        checkout, deleted = await _queued(
            db_engine,
            _CART,
            [_post(client, CHECKOUT, checkout_body(), key=True), _delete(client)],
            u=user.id,
        )
    finally:
        await client.aclose()
    assert checkout.status_code == 201, checkout.text
    _refused(deleted, 409, reason="open_order")
    assert await _orders(db_engine, user.id) == 1 and not await _anonymised(db_engine, user.id)


_OFFER = "SELECT id FROM offers WHERE id = :o FOR UPDATE"
OFFER_BODY = {"accept_terms": True, "accept_digital_final_sale": True}


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "checkout_first"])
async def test_deletion_racing_an_offer_checkout_never_deadlocks_or_orphans_an_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    """The checkout's order INSERT holds KEY SHARE on `users` while it waits on the offer;
    the deletion's NO KEY UPDATE on `users` must not wait on it (ADR-047)."""
    user = await create_user(db_session)
    offer = await seed_offer(
        db_session,
        user_id=user.id,
        product_id=await stl(db_session),
        status="accepted",
        responds_by=None,
    )
    client = await _client(app, user.email)
    pay = _post(client, f"/api/v1/me/offers/{offer}/checkout", OFFER_BODY, key=True)
    racers = [_delete(client), pay] if deletion_first else [pay, _delete(client)]
    try:
        first, second = await _queued(db_engine, _OFFER, racers, o=offer)
    finally:
        await client.aclose()
    deleted, checkout = (first, second) if deletion_first else (second, first)
    if deletion_first:
        assert deleted.status_code == 204, deleted.text
        assert checkout.status_code == 409, checkout.text  # the withdrawn offer refuses it
        assert checkout.json()["offer_status"] == "withdrawn"
        assert await _orders(db_engine, user.id) == 0
        status = await scalar(db_engine, "SELECT status FROM offers WHERE id = :o", o=offer)
        assert status == "withdrawn"
    else:
        assert checkout.status_code == 201, checkout.text
        _refused(deleted, 409, reason="open_order")
        assert not await _anonymised(db_engine, user.id)


_ORDER = "SELECT id FROM orders WHERE id = :o FOR UPDATE"


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "report_first"])
async def test_deletion_racing_a_problem_report_keeps_no_personal_data(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=user.id,
        line_states=["delivered"],
        order_status="completed",
        payment_method="online",
        payment_status="paid",
        email=user.email,
    )
    client = await _client(app, user.email)
    report = _post(client, f"/api/v1/me/orders/{order.order_id}/report-problem", {"message": "Hi"})
    racers = [_delete(client), report] if deletion_first else [report, _delete(client)]
    try:
        first, second = await _queued(db_engine, _ORDER, racers, o=order.order_id)
    finally:
        await client.aclose()
    deleted, reported = (first, second) if deletion_first else (second, first)
    assert deleted.status_code == 204, deleted.text
    assert reported.status_code == (401 if deletion_first else 201), reported.text
    messages = await scalar(
        db_engine, "SELECT count(*) FROM contact_messages WHERE user_id = :u", u=user.id
    )
    assert messages == (0 if deletion_first else 1)
    leaked = await scalar(
        db_engine, "SELECT count(*) FROM contact_messages WHERE email = :e", e=user.email
    )
    assert leaked == 0


_USER = "SELECT id FROM users WHERE id = :u FOR NO KEY UPDATE"  # the address-book lock
ADDRESS = {
    "label": "Home",
    "recipient_name": "Rana",
    "phone": "+96171123456",
    "governorate": "beqaa",
    "city": "Zahle",
    "landmark_notes": "Blue door",
}


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "address_first"])
async def test_deletion_racing_an_address_create_leaves_no_live_address(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    user = await create_user(db_session)
    client = await _client(app, user.email)
    create = _post(client, "/api/v1/me/addresses", ADDRESS)
    racers = [_delete(client), create] if deletion_first else [create, _delete(client)]
    try:
        first, second = await _queued(db_engine, _USER, racers, u=user.id)
    finally:
        await client.aclose()
    deleted, created = (first, second) if deletion_first else (second, first)
    assert deleted.status_code == 204, deleted.text
    # The deletion already holds KEY SHARE on `users` (its cart INSERT), so Postgres may grant
    # either waiter first: each outcome must leave no address with personal data.
    row = await one(
        db_engine,
        "SELECT count(*) AS n, count(*) FILTER (WHERE phone IS NOT NULL) AS with_phone"
        " FROM addresses WHERE user_id = :u",
        u=user.id,
    )
    assert (created.status_code, row.n, row.with_phone) in {(401, 0, 0), (201, 1, 0)}, created.text


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "refund_first"])
async def test_deletion_racing_an_admin_refund_blocks_or_lets_it_land(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    """FR-03: a refund issued first blocks the deletion (BR-126); one issued after lands on
    the anonymised order. Both lock the order first, so no deadlock."""
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=user.id,
        line_states=["delivered"],
        order_status="completed",
        payment_method="online",
        payment_status="paid",
        email=user.email,
    )
    client = await _client(app, user.email)
    admin, _ = await admin_client(app, db_session)
    body = {
        "items": [{"order_item_id": str(order.line_ids[0]), "amount_cents": 300}],
        "reason": "Goodwill",
    }
    refund = _post(admin, f"/api/v1/admin/orders/{order.order_id}/refunds", body, key=True)
    racers = [_delete(client), refund] if deletion_first else [refund, _delete(client)]
    try:
        first, second = await _queued(db_engine, _ORDER, racers, o=order.order_id)
    finally:
        await client.aclose()
        await admin.aclose()
    deleted, refunded = (first, second) if deletion_first else (second, first)
    assert refunded.status_code == 201, refunded.text
    if deletion_first:
        assert deleted.status_code == 204, deleted.text
    else:
        _refused(deleted, 409, reason="unsettled_refund")
    assert await _anonymised(db_engine, user.id) is deletion_first


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "checkout_first"])
async def test_deletion_racing_a_cash_checkout_never_orphans_an_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    """Cash checkout locks the cart first too (ADR-024 d9), before the cash phone."""
    user = await create_user(db_session)
    client = await _client(app, user.email)
    added = await client.post(
        ITEMS, json={"product_id": str(await physical(db_session))}, headers=_headers(client)
    )
    assert added.status_code == 200, added.text
    pay = _post(client, CHECKOUT, pickup_body(random_phone()), key=True)
    racers = [_delete(client), pay] if deletion_first else [pay, _delete(client)]
    try:
        async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
            first, second = await _queued(db_engine, _CART, racers, u=user.id)
    finally:
        await client.aclose()
    deleted, checkout = (first, second) if deletion_first else (second, first)
    if deletion_first:
        assert deleted.status_code == 204, deleted.text
        _refused(checkout, 401, code="AUTH_REQUIRED")
        assert await _orders(db_engine, user.id) == 0 and await _anonymised(db_engine, user.id)
    else:
        assert checkout.status_code == 201, checkout.text
        _refused(deleted, 409, reason="open_order")
        assert await _orders(db_engine, user.id) == 1 and not await _anonymised(db_engine, user.id)


@pytest.mark.parametrize("deletion_first", [True, False], ids=["deletion_first", "accept_first"])
async def test_deletion_racing_a_counter_offer_accept_leaves_the_offer_withdrawn(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, deletion_first: bool
) -> None:
    """An accepted offer is still live, so deletion withdraws it either way; an accept queued
    behind the deletion finds it withdrawn."""
    user = await create_user(db_session)
    offer = await seed_offer(
        db_session, user_id=user.id, product_id=await stl(db_session), status="awaiting_customer"
    )
    client = await _client(app, user.email)
    accept = _post(client, f"/api/v1/me/offers/{offer}/accept", {"expected_amount_cents": 800})
    racers = [_delete(client), accept] if deletion_first else [accept, _delete(client)]
    try:
        first, second = await _queued(db_engine, _OFFER, racers, o=offer)
    finally:
        await client.aclose()
    deleted, accepted = (first, second) if deletion_first else (second, first)
    assert deleted.status_code == 204, deleted.text
    assert accepted.status_code == (409 if deletion_first else 200), accepted.text
    state = await one(db_engine, "SELECT status, turn FROM offers WHERE id = :o", o=offer)
    assert (state.status, state.turn) == ("withdrawn", None)
    assert await _anonymised(db_engine, user.id)


async def test_an_offer_checkout_refuses_an_account_closed_while_it_waited(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-047 d7's backstop (audit A-02). No known race reaches it, as deletion withdraws the
    offer first, so the account is closed by hand while the checkout waits on its offer."""
    user = await create_user(db_session)
    offer = await seed_offer(
        db_session,
        user_id=user.id,
        product_id=await stl(db_session),
        status="accepted",
        responds_by=None,
    )
    client = await _client(app, user.email)
    pay = _post(client, f"/api/v1/me/offers/{offer}/checkout", OFFER_BODY, key=True)
    try:
        async with _held(db_engine, _OFFER, o=offer) as held:
            checkout = asyncio.create_task(pay())
            await wait_for_waiters(db_engine, 1)
            closing = text("UPDATE users SET is_active = false WHERE id = :u")
            async with db_engine.begin() as conn:
                await asyncio.wait_for(conn.execute(closing, {"u": user.id}), timeout=5)
            await held.commit()
        response = await asyncio.wait_for(checkout, timeout=RACE_TIMEOUT_SECONDS)
    finally:
        await client.aclose()
    _refused(response, 401, code="AUTH_REQUIRED")
    assert await _orders(db_engine, user.id) == 0
