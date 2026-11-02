"""The `manual` open-order cap at its limit (VS-050 audit Q-1, ADR-049 d14), through the
real routes on one running app: a cart checkout and an offer checkout by one customer."""

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

from app.ordering.domain.manual_orders import MANUAL_ORDERS_LOCK_NS
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.infrastructure.providers.manual import ManualPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import SYNC_TIMEOUT_SECONDS, meet_or_fail
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.negotiation.offer_support import seed_offer
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    ITEMS,
    checkout_body,
    new_key,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import random_phone, setting, stl

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
HOLD_SECONDS = 0.3
OPEN_MANUAL = """
    SELECT count(*) FROM orders o JOIN payments p ON p.order_id = o.id
    WHERE o.user_id = :u AND o.status = 'pending_payment' AND p.provider = 'manual'
"""


@pytest_asyncio.fixture
async def app(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    async with (
        setting(db_engine, "manual_max_open_orders", 1),
        running_app(make_app) as running,
    ):
        monkeypatch.setattr(running.state, "payment_providers", {"manual": ManualPaymentProvider()})
        yield running


async def _signed_in(app: FastAPI, email: str) -> httpx.AsyncClient:
    client = async_client(app)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client


def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"], "Idempotency-Key": new_key()}


async def _advisory_wait(engine: AsyncEngine) -> None:
    """Return once a backend waits for an advisory lock, or fail: the race did not happen."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SYNC_TIMEOUT_SECONDS
    while loop.time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE NOT granted AND locktype = 'advisory'"
                    " AND classid = :ns AND objsubid = 2"
                ),
                {"ns": MANUAL_ORDERS_LOCK_NS},
            )
        if waiting:
            return
        await asyncio.sleep(0.02)
    pytest.fail("no checkout ever waited for the customer's manual-cap lock")


async def test_a_cart_and_an_offer_checkout_at_the_cap_place_one_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both count under the customer's lock; without it both would read 0 and both place."""
    barrier = asyncio.Barrier(2)
    lock, unpaid = SqlOrderStore.lock_manual_orders, SqlOrderStore.unpaid_online_order_ids

    async def synced(self: SqlOrderStore, user_id: uuid.UUID) -> None:
        await meet_or_fail(barrier)
        await lock(self, user_id)

    async def slow_unpaid(self: SqlOrderStore, user_id: uuid.UUID) -> Any:
        found = await unpaid(self, user_id)
        await asyncio.sleep(HOLD_SECONDS)
        return found

    monkeypatch.setattr(SqlOrderStore, "lock_manual_orders", synced)
    monkeypatch.setattr(SqlOrderStore, "unpaid_online_order_ids", slow_unpaid)
    customer = await create_user(db_session)
    model, other = await stl(db_session), await stl(db_session)
    offer = await seed_offer(
        db_session, user_id=customer.id, product_id=other, status="accepted", responds_by=None
    )
    cart, offers = (
        await _signed_in(app, customer.email),
        await _signed_in(app, customer.email),
    )
    try:
        added = await cart.post(ITEMS, json={"product_id": str(model)}, headers=_headers(cart))
        assert added.status_code == 200, added.text
        offer_body = {
            "accept_terms": True,
            "accept_digital_final_sale": True,
            "contact_phone": random_phone(),
        }
        responses = await asyncio.gather(
            cart.post(
                CHECKOUT,
                json=checkout_body(contact_phone=random_phone()),
                headers=_headers(cart),
            ),
            offers.post(
                f"/api/v1/me/offers/{offer}/checkout", json=offer_body, headers=_headers(offers)
            ),
            _advisory_wait(db_engine),
        )
    finally:
        await cart.aclose()
        await offers.aclose()
    placed = responses[:2]
    assert sorted(r.status_code for r in placed) == [201, 422], [r.text for r in placed]
    loser = next(r for r in placed if r.status_code == 422)
    assert loser.json()["code"] == "MANUAL_ORDER_LIMIT_REACHED"
    async with db_engine.connect() as conn:
        assert await conn.scalar(text(OPEN_MANUAL), {"u": customer.id}) == 1
