"""VS-028 cash checkout races R1-R5 (plan 6.3, 8.1) through the real route on one running app.
Racers meet at a barrier or hold a lock at an event, and each wait is proved through
`pg_locks`, so a race that silently ran in sequence fails instead of passing."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.security import hash_phone
from app.ordering.api import checkout as checkout_api
from app.ordering.application.services import cart as cart_service
from app.ordering.application.services import checkout as checkout_service
from app.ordering.infrastructure.cash import SqlCashChecks
from app.ordering.infrastructure.checkout_addresses import SqlCheckoutAddresses
from app.ordering.infrastructure.orders import SqlOrderStore
from app.ordering.public import lock_order_for_change, release_unpaid_order
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import SYNC_TIMEOUT_SECONDS, meet_or_fail
from tests.concurrency.cash_block_support import cancel_with_block
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    ITEMS,
    new_key,
    rows,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    delivery_body,
    physical,
    pickup_body,
    random_phone,
    seed_address,
    seed_cash_order,
    setting,
    spaced,
)
from tests.integration.payments.recovery_support import seed_attempt, seed_order

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
HOLD_SECONDS = 0.3
ITERATIONS = 20
DEADLOCK = "40P01"


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI], db_engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    async with (
        setting(db_engine, "pickup_address", "Workshop, Zahle"),
        running_app(make_app) as running,
    ):
        yield running


async def _buyer(
    app: FastAPI, db: AsyncSession, *products: uuid.UUID, user_id: uuid.UUID | None = None
) -> tuple[httpx.AsyncClient, uuid.UUID]:
    if user_id is None:
        user = await create_user(db)
        email, user_id = user.email, user.id
    else:
        email = (
            await db.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user_id})
        ).scalar_one()
    client = async_client(app)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    for product_id in products:
        added = await client.post(
            ITEMS, json={"product_id": str(product_id)}, headers=_csrf(client)
        )
        assert added.status_code == 200, added.text
    return client, user_id


def _csrf(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


async def _checkout(
    client: httpx.AsyncClient, body: dict[str, Any], key: str | None = None
) -> httpx.Response:
    return await client.post(
        CHECKOUT, json=body, headers=_csrf(client) | {"Idempotency-Key": key or new_key()}
    )


async def _waiting(engine: AsyncEngine, locktype: str | None = None) -> None:
    """Return once some backend waits for a lock (of `locktype`), or fail the test."""
    sql = "SELECT count(*) FROM pg_locks WHERE NOT granted" + (
        " AND locktype = :t" if locktype else ""
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SYNC_TIMEOUT_SECONDS
    while loop.time() < deadline:
        async with engine.connect() as conn:
            if await conn.scalar(text(sql), {"t": locktype}):
                return
        await asyncio.sleep(0.02)
    pytest.fail(f"no backend ever waited for a {locktype or 'row'} lock: the race did not happen")


async def _cash_orders_for(engine: AsyncEngine, phone: str) -> int:
    sql = (
        "SELECT count(*) FROM orders WHERE payment_method = 'cash' AND contact_phone_hash = :h"
        " AND status = 'in_progress'"
    )
    async with engine.connect() as conn:
        return int(await conn.scalar(text(sql), {"h": hash_phone(phone)}) or 0)


def _no_deadlock(*responses: httpx.Response) -> None:
    for response in responses:
        assert response.status_code != 500, response.text
        assert DEADLOCK not in response.text


# ------------------------------------------------------------------- R1


@pytest.mark.parametrize("fulfillment", ["pickup", "delivery"])
async def test_r1_two_accounts_one_phone_place_one_cash_order(
    app: FastAPI,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    fulfillment: str,
) -> None:
    """Both read the open-order count under the phone lock; without it both would read 0."""
    barrier = asyncio.Barrier(2)
    lock_cart, count = cart_service.lock_cart_for_checkout, SqlCashChecks.open_order_count

    async def synced(*args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await lock_cart(*args, **kwargs)

    async def slow_count(self: SqlCashChecks, *args: Any, **kwargs: Any) -> int:
        found = await count(self, *args, **kwargs)
        await asyncio.sleep(HOLD_SECONDS)
        return found

    monkeypatch.setattr(checkout_service, "lock_cart_for_checkout", synced)
    monkeypatch.setattr(SqlCashChecks, "open_order_count", slow_count)
    lamp, phone = await physical(db_session), random_phone()
    (first, a), (second, b) = (
        await _buyer(app, db_session, lamp),
        await _buyer(app, db_session, lamp),
    )
    if fulfillment == "pickup":
        bodies = [pickup_body(phone), pickup_body(spaced(phone))]
    else:
        bodies = [
            delivery_body(await seed_address(db_session, a, phone)),
            delivery_body(await seed_address(db_session, b, phone)),
        ]
    try:
        responses = await asyncio.gather(_checkout(first, bodies[0]), _checkout(second, bodies[1]))
    finally:
        await first.aclose()
        await second.aclose()
    _no_deadlock(*responses)
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    loser = next(r for r in responses if r.status_code == 422)
    assert loser.json()["code"] == "CASH_NOT_AVAILABLE"
    assert await _cash_orders_for(db_engine, phone) == 1


# ------------------------------------------------------------------- R2


async def test_r2_one_customer_two_keys_place_one_cash_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = asyncio.Barrier(2)
    lock_cart = cart_service.lock_cart_for_checkout

    async def synced(*args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        locked = await lock_cart(*args, **kwargs)
        await asyncio.sleep(HOLD_SECONDS)
        return locked

    monkeypatch.setattr(checkout_service, "lock_cart_for_checkout", synced)
    client, user_id = await _buyer(app, db_session, await physical(db_session))
    phone = random_phone()
    try:
        responses = await asyncio.gather(
            _checkout(client, pickup_body(phone)), _checkout(client, pickup_body(phone))
        )
    finally:
        await client.aclose()
    _no_deadlock(*responses)
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    assert next(r for r in responses if r.status_code == 409).json()["code"] == "CART_EMPTY"
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 0, 1, 0)


async def test_r2_b_one_key_in_parallel_places_one_cash_order_and_replays_it(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cash claim completes inside its one transaction, so the twin waiting on the claim
    replays the 201 and never sees it in progress."""
    barrier = asyncio.Barrier(2)
    claim, place = SqlIdempotencyStore.claim, checkout_service.place_order

    async def synced_claim(self: SqlIdempotencyStore, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await claim(self, **kwargs)

    async def held_place(**kwargs: Any) -> Any:
        placed = await place(**kwargs)
        await _waiting(db_engine, "transactionid")  # the twin is blocked on this claim
        return placed

    monkeypatch.setattr(SqlIdempotencyStore, "claim", synced_claim)
    monkeypatch.setattr(checkout_api, "place_order", held_place)
    client, user_id = await _buyer(app, db_session, await physical(db_session))
    key, body = new_key(), pickup_body(random_phone())
    try:
        responses = await asyncio.gather(_checkout(client, body, key), _checkout(client, body, key))
    finally:
        await client.aclose()
    _no_deadlock(*responses)
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    replayed = sorted(r.headers.get("idempotent-replayed", "false") for r in responses)
    assert replayed == ["false", "true"]
    assert responses[0].json() == responses[1].json()
    counts = await rows(db_engine, user_id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 0, 1, 0)


# ------------------------------------------------------------------- R3


async def _r3_setup(
    app: FastAPI, db: AsyncSession, *, same_customer: bool
) -> tuple[httpx.AsyncClient, uuid.UUID, uuid.UUID, uuid.UUID, str, str]:
    """X has an open cash order on phone P. The checkout is by another account on P (a),
    or by X itself on another phone (b). Returns client, its user, X, X's order, P, the
    checkout's phone."""
    lamp, phone = await physical(db), random_phone()
    holder = await create_user(db)
    order_id = await seed_cash_order(db, holder.id, phone)
    if same_customer:
        client, user_id = await _buyer(app, db, lamp, user_id=holder.id)
        return client, user_id, holder.id, order_id, phone, random_phone()
    client, user_id = await _buyer(app, db, lamp)
    return client, user_id, holder.id, order_id, phone, phone


@pytest.mark.parametrize(
    ("variant", "waits_on"), [("a", "advisory"), ("b", None)], ids=["phone", "cart"]
)
async def test_r3_a_block_committed_first_refuses_the_waiting_checkout(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, variant: str, waits_on: str
) -> None:
    """(a) another account, same phone: the checkout waits on the phone lock. (b) the same
    customer, another phone: it waits on the cart lock. Either way it is refused after."""
    async with setting(db_engine, "cash_max_open_orders", 2):
        for _ in range(ITERATIONS):
            client, user_id, holder, order_id, phone, typed = await _r3_setup(
                app, db_session, same_customer=variant == "b"
            )
            holding, release = asyncio.Event(), asyncio.Event()
            cancel = asyncio.create_task(
                cancel_with_block(
                    db_engine,
                    order_id=order_id,
                    user_id=holder,
                    phone_hash=hash_phone(phone),
                    holding=holding,
                    release=release,
                )
            )
            try:
                await asyncio.wait_for(holding.wait(), timeout=SYNC_TIMEOUT_SECONDS)
                checkout = asyncio.create_task(_checkout(client, pickup_body(typed)))
                await _waiting(db_engine, waits_on)
                release.set()
                await asyncio.wait_for(cancel, timeout=5)
                response = await asyncio.wait_for(checkout, timeout=5)
            finally:
                release.set()
                await client.aclose()
            _no_deadlock(response)
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "CASH_NOT_AVAILABLE"
            orders = await rows(db_engine, user_id)
            assert orders.orders == (1 if variant == "b" else 0)  # (b): only X's seeded order


async def test_r3_c_a_checkout_holding_the_phone_lock_commits_before_the_block(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reverse: the cancel waits on the phone lock, the order commits first, then the
    block is inserted. One order and one block, the permitted order of events."""
    holding, release = asyncio.Event(), asyncio.Event()
    count = SqlCashChecks.open_order_count

    async def held(self: SqlCashChecks, *args: Any, **kwargs: Any) -> int:
        found = await count(self, *args, **kwargs)
        holding.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        return found

    monkeypatch.setattr(SqlCashChecks, "open_order_count", held)
    async with setting(db_engine, "cash_max_open_orders", 2):
        for _ in range(ITERATIONS):
            holding.clear()
            release.clear()
            client, user_id, holder, order_id, phone, typed = await _r3_setup(
                app, db_session, same_customer=False
            )
            checkout = asyncio.create_task(_checkout(client, pickup_body(typed)))
            try:
                await asyncio.wait_for(holding.wait(), timeout=SYNC_TIMEOUT_SECONDS)
                cancel = asyncio.create_task(
                    cancel_with_block(
                        db_engine, order_id=order_id, user_id=holder, phone_hash=hash_phone(phone)
                    )
                )
                await _waiting(db_engine, "advisory")
                release.set()
                response = await asyncio.wait_for(checkout, timeout=5)
                await asyncio.wait_for(cancel, timeout=5)
            finally:
                release.set()
                await client.aclose()
            _no_deadlock(response)
            assert response.status_code == 201, response.text
            async with db_engine.connect() as conn:
                blocks = await conn.scalar(
                    text("SELECT count(*) FROM cash_payment_blocks WHERE order_id = :o"),
                    {"o": order_id},
                )
            assert (await rows(db_engine, user_id)).orders == 1
            assert blocks == 1


# ------------------------------------------------------------------- R4


async def test_r4_an_address_delete_waits_for_the_checkout_holding_it_for_share(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delete's UPDATE waits on the FOR SHARE lock; the order keeps the pre-delete row."""
    holding, release = asyncio.Event(), asyncio.Event()
    lock_for_share = SqlCheckoutAddresses.lock_for_share

    async def held(self: SqlCheckoutAddresses, *args: Any) -> Any:
        found = await lock_for_share(self, *args)
        holding.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        return found

    monkeypatch.setattr(SqlCheckoutAddresses, "lock_for_share", held)
    for _ in range(5):
        holding.clear()
        release.clear()
        client, user_id = await _buyer(app, db_session, await physical(db_session))
        address = await seed_address(db_session, user_id, recipient_name="Before Delete")
        checkout = asyncio.create_task(_checkout(client, delivery_body(address)))
        try:
            await asyncio.wait_for(holding.wait(), timeout=SYNC_TIMEOUT_SECONDS)
            delete = asyncio.create_task(
                client.delete(f"/api/v1/me/addresses/{address}", headers=_csrf(client))
            )
            await _waiting(db_engine)
            release.set()
            response = await asyncio.wait_for(checkout, timeout=5)
            deleted = await asyncio.wait_for(delete, timeout=5)
        finally:
            release.set()
            await client.aclose()
        _no_deadlock(response, deleted)
        assert response.status_code == 201, response.text
        assert deleted.status_code == 204, deleted.text
        snapshot = response.json()["order"]["delivery_address"]
        assert snapshot["recipient_name"] == "Before Delete"


# ------------------------------------------------------------------- R5


async def _other_unpaid_order(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    placed = datetime.now(UTC) - timedelta(minutes=5)
    order = await seed_order(db, placed_at=placed, user_id=user_id)
    await seed_attempt(db, order, initiated_at=placed, status="failed")
    return order.order_id


async def test_r5_a_cash_checkout_never_waits_on_a_release_holding_another_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """D5: checkout takes no existing `orders` row, so it completes while a release holds
    the customer's other order; then the release finishes. Neither waits on the other."""
    client, user_id = await _buyer(app, db_session, await physical(db_session))
    other = await _other_unpaid_order(db_session, user_id)
    holding, release = asyncio.Event(), asyncio.Event()

    async def releasing() -> tuple[uuid.UUID, ...]:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            locked = await lock_order_for_change(session, other)
            assert locked is not None
            holding.set()
            await asyncio.wait_for(release.wait(), timeout=10)
            return await release_unpaid_order(
                session, locked, at=datetime.now(UTC), reason="hold_expired"
            )

    job = asyncio.create_task(releasing())
    try:
        await asyncio.wait_for(holding.wait(), timeout=SYNC_TIMEOUT_SECONDS)
        response = await asyncio.wait_for(_checkout(client, pickup_body(random_phone())), timeout=5)
        release.set()
        await asyncio.wait_for(job, timeout=5)
    finally:
        release.set()
        await client.aclose()
    _no_deadlock(response)
    assert response.status_code == 201, response.text
    async with db_engine.connect() as conn:
        status = await conn.scalar(text("SELECT status FROM orders WHERE id = :o"), {"o": other})
    assert status == "cancelled"
    assert (await rows(db_engine, user_id)).orders == 2


async def test_r5_a_cash_checkout_never_waits_on_a_payment_retry_holding_another_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real retry route holds the other order FOR UPDATE at an event; the cash checkout
    completes meanwhile, then the retry opens its new attempt."""
    holding, release = asyncio.Event(), asyncio.Event()
    lock_owned = SqlOrderStore.lock_owned_order

    async def held(self: SqlOrderStore, *args: Any) -> Any:
        found = await lock_owned(self, *args)
        holding.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        return found

    monkeypatch.setattr(SqlOrderStore, "lock_owned_order", held)
    client, user_id = await _buyer(app, db_session, await physical(db_session))
    other = await _other_unpaid_order(db_session, user_id)
    retry = asyncio.create_task(
        client.post(
            f"/api/v1/me/orders/{other}/payments",
            json={},
            headers=_csrf(client) | {"Idempotency-Key": new_key()},
        )
    )
    try:
        await asyncio.wait_for(holding.wait(), timeout=SYNC_TIMEOUT_SECONDS)
        response = await asyncio.wait_for(_checkout(client, pickup_body(random_phone())), timeout=5)
        release.set()
        retried = await asyncio.wait_for(retry, timeout=5)
    finally:
        release.set()
        await client.aclose()
    _no_deadlock(response, retried)
    assert response.status_code == 201, response.text
    assert retried.status_code == 201, retried.text
    assert (await rows(db_engine, user_id)).orders == 2
