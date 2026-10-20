"""VS-041 races on real PostgreSQL (ADR-037): racers meet at a barrier where it matters and
a stagger picks who goes first. Invariants: one owning line, a paid offer never expired,
no live offer on an owned STL, no deadlock."""

import asyncio
import contextvars
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

from app.jobs.expire_offers import expire_offers
from app.negotiation.infrastructure.adapters import OrderingStlOwnership
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.negotiation.public import SqlOfferCheckouts
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure import ordering_side
from app.payments.infrastructure.order_payments import SqlPaymentInFlight
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.negotiation.offer_checkout_support import pay, seed_order_with_attempt
from tests.integration.negotiation.offer_support import (
    OFFERS,
    offer_state,
    seed_offer,
    shop_open,  # noqa: F401
    stl,
)
from tests.integration.ordering.checkout_support import CHECKOUT, ITEMS, checkout_body, new_key

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
STAGGER = 0.3
OFFER_BODY = {"accept_terms": True, "accept_digital_final_sale": True}
_delay: contextvars.ContextVar[float] = contextvars.ContextVar("delay", default=0.0)
# The name the payment's apply path calls, patched per test (re-exported, not defined, there).
_SETTLE_REAL = getattr(ordering_side, "settle_offers_on_stl_purchase")  # noqa: B009


@pytest_asyncio.fixture
async def app(make_app: Callable[[], FastAPI]) -> AsyncIterator[FastAPI]:
    async with running_app(make_app) as running:
        yield running


async def _client(app: FastAPI, email: str) -> httpx.AsyncClient:
    client = async_client(app)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client


def _csrf(client: httpx.AsyncClient, key: bool = True) -> dict[str, str]:
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    return headers | ({"Idempotency-Key": new_key()} if key else {})


async def _offer_checkout(client: httpx.AsyncClient, offer: uuid.UUID) -> httpx.Response:
    return await client.post(
        f"/api/v1/me/offers/{offer}/checkout", json=OFFER_BODY, headers=_csrf(client)
    )


async def _as(delay: float, work: Callable[[], Any]) -> Any:
    _delay.set(delay)
    return await work()


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


def _sync_inserts(monkeypatch: pytest.MonkeyPatch, racers: int) -> None:
    """Every racer reaches the order-line INSERT (the ownership index) together."""
    barrier = asyncio.Barrier(racers)
    real = SqlOrderStore.insert_lines

    async def synced(self: SqlOrderStore, *args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await real(self, *args, **kwargs)

    monkeypatch.setattr(SqlOrderStore, "insert_lines", synced)


async def _live_lines(engine: AsyncEngine, user: uuid.UUID, product: uuid.UUID) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                "SELECT count(*) FROM order_items WHERE user_id = :u AND product_id = :p"
                " AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')"
            ),
            {"u": user, "p": product},
        )
    return int(count or 0)


async def _accepted(db: AsyncSession, **over: Any) -> tuple[Any, uuid.UUID, uuid.UUID]:
    user = await create_user(db)
    product = await stl(db)
    offer = await seed_offer(
        db, user_id=user.id, product_id=product, status="accepted", responds_by=None, **over
    )
    return user, product, offer


# ----------------------------------------------------------- checkout vs checkout


async def test_offer_checkout_racing_cart_checkout_yields_one_owning_line(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, product, offer = await _accepted(db_session)
    client = await _client(app, user.email)
    added = await client.post(
        ITEMS, json={"product_id": str(product)}, headers=_csrf(client, False)
    )
    assert added.status_code == 200, added.text
    _sync_inserts(monkeypatch, 2)
    try:
        by_offer, by_cart = await asyncio.gather(
            _offer_checkout(client, offer),
            client.post(CHECKOUT, json=checkout_body(), headers=_csrf(client)),
        )
    finally:
        await client.aclose()
    assert sorted((by_offer.status_code, by_cart.status_code)) == [201, 409]
    loser = by_offer if by_offer.status_code == 409 else by_cart
    assert loser.json()["code"] == "PRODUCT_ALREADY_OWNED", loser.text
    assert await _live_lines(db_engine, user.id, product) == 1


async def test_two_offer_checkouts_of_one_offer_place_one_order(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, product, offer = await _accepted(db_session)
    client = await _client(app, user.email)
    _sync_inserts(monkeypatch, 2)
    try:
        responses = await asyncio.gather(
            _offer_checkout(client, offer), _offer_checkout(client, offer)
        )
    finally:
        await client.aclose()
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    assert await _live_lines(db_engine, user.id, product) == 1
    async with db_engine.connect() as conn:
        payments = await conn.scalar(
            text(
                "SELECT count(*) FROM payments p JOIN orders o ON o.id = p.order_id"
                " WHERE o.user_id = :u"
            ),
            {"u": user.id},
        )
    assert payments == 1


# ------------------------------------------------------- the job vs money moving


@pytest.mark.parametrize("first", ["job", "payment"])
async def test_the_window_closing_while_a_payment_is_applied_ends_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, first: str
) -> None:
    """The job holds the offer and reads the attempt; the payment holds orders, lines and
    payment and wants the offer. The attempt reads live, so the offer is never expired."""
    closed = datetime.now(UTC) - timedelta(seconds=1)
    user, product, offer = await _accepted(db_session, checkout_expires_at=closed)
    _, payment = await seed_order_with_attempt(
        db_session, user_id=user.id, product_id=product, offer_id=offer
    )
    barrier = asyncio.Barrier(2)
    real_in_flight, real_settle = (
        SqlPaymentInFlight.in_flight,
        _SETTLE_REAL,
    )

    async def job_side(self: SqlPaymentInFlight, offer_id: uuid.UUID) -> bool:
        if offer_id == offer:  # other tests' overdue offers pass straight through
            await meet_or_fail(barrier)
            await asyncio.sleep(_delay.get())
        return await real_in_flight(self, offer_id)

    async def payment_side(*args: Any, **kwargs: Any) -> None:
        await meet_or_fail(barrier)
        await asyncio.sleep(_delay.get())
        await real_settle(*args, **kwargs)

    monkeypatch.setattr(SqlPaymentInFlight, "in_flight", job_side)
    monkeypatch.setattr(ordering_side, "settle_offers_on_stl_purchase", payment_side)
    job_delay, pay_delay = (0.0, STAGGER) if first == "job" else (STAGGER, 0.0)
    _, outcome = await asyncio.gather(
        _as(job_delay, lambda: expire_offers(_ctx(db_engine), now=datetime.now(UTC))),
        _as(pay_delay, lambda: pay(db_engine, payment)),
    )
    assert outcome is Outcome.APPLY_PAID
    state = await offer_state(db_engine, offer)
    assert state["status"] == "paid", state["rounds"]


@pytest.mark.parametrize("first", ["job", "retry"])
async def test_the_window_closing_while_a_retry_starts_never_leaves_an_expired_offer_paying(
    app: FastAPI,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    closes = datetime.now(UTC) + timedelta(seconds=30)
    user, product, offer = await _accepted(db_session, checkout_expires_at=closes)
    order, _ = await seed_order_with_attempt(
        db_session, user_id=user.id, product_id=product, offer_id=offer, attempt="failed"
    )
    barrier = asyncio.Barrier(2)
    real_lock, real_skip = SqlOfferCheckouts.lock, SqlOfferStore.lock_unless_locked

    async def retry_side(self: SqlOfferCheckouts, *args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        await asyncio.sleep(_delay.get())
        return await real_lock(self, *args, **kwargs)

    async def job_side(self: SqlOfferStore, offer_id: uuid.UUID) -> Any:
        if offer_id == offer:
            await meet_or_fail(barrier)
            await asyncio.sleep(_delay.get())
        return await real_skip(self, offer_id)

    monkeypatch.setattr(SqlOfferCheckouts, "lock", retry_side)
    monkeypatch.setattr(SqlOfferStore, "lock_unless_locked", job_side)
    client = await _client(app, user.email)

    async def retry() -> httpx.Response:
        return await client.post(
            f"/api/v1/me/orders/{order}/payments", json={}, headers=_csrf(client)
        )

    job_delay, retry_delay = (0.0, STAGGER) if first == "job" else (STAGGER, 0.0)
    try:
        _, response = await asyncio.gather(
            _as(job_delay, lambda: expire_offers(_ctx(db_engine), now=closes)),
            _as(retry_delay, retry),
        )
    finally:
        await client.aclose()
    status = (await offer_state(db_engine, offer))["status"]
    async with db_engine.connect() as conn:
        live = await conn.scalar(
            text(
                "SELECT count(*) FROM payments WHERE order_id = :o"
                " AND status IN ('pending', 'processing')"
            ),
            {"o": order},
        )
    if first == "job":
        assert (status, live, response.status_code) == ("checkout_expired", 0, 409), response.text
        assert response.json()["reason"] == "offer_checkout_expired"
    else:
        assert (status, live, response.status_code) == ("accepted", 1, 201), response.text


@pytest.mark.parametrize("first", ["job", "checkout"])
async def test_the_window_closing_while_offer_checkout_places_its_order(
    app: FastAPI,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    """Checkout passed the unlocked read. Its line's FK takes KEY SHARE on the offer, so the
    barrier sits before that INSERT; the re-check under the offer lock then decides."""
    closes = datetime.now(UTC) + timedelta(seconds=30)
    user, _, offer = await _accepted(db_session, checkout_expires_at=closes)
    barrier = asyncio.Barrier(2)
    real_insert, real_skip = SqlOrderStore.insert_lines, SqlOfferStore.lock_unless_locked

    async def checkout_side(self: SqlOrderStore, *args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        await asyncio.sleep(_delay.get())
        return await real_insert(self, *args, **kwargs)

    async def job_side(self: SqlOfferStore, offer_id: uuid.UUID) -> Any:
        if offer_id == offer:
            await meet_or_fail(barrier)
            await asyncio.sleep(_delay.get())
        return await real_skip(self, offer_id)

    monkeypatch.setattr(SqlOrderStore, "insert_lines", checkout_side)
    monkeypatch.setattr(SqlOfferStore, "lock_unless_locked", job_side)
    client = await _client(app, user.email)
    job_delay, checkout_delay = (0.0, STAGGER) if first == "job" else (STAGGER, 0.0)
    try:
        _, response = await asyncio.gather(
            _as(job_delay, lambda: expire_offers(_ctx(db_engine), now=closes)),
            _as(checkout_delay, lambda: _offer_checkout(client, offer)),
        )
    finally:
        await client.aclose()
    status = (await offer_state(db_engine, offer))["status"]
    async with db_engine.connect() as conn:
        orders = await conn.scalar(
            text("SELECT count(*) FROM orders WHERE user_id = :u"), {"u": user.id}
        )
    if first == "job":
        assert (status, orders, response.status_code) == ("checkout_expired", 0, 410)
    else:
        assert (status, orders, response.status_code) == ("accepted", 1, 201), response.text


# ------------------------------------------------------ acquisition vs the offer


async def test_a_submission_racing_a_cart_payment_never_leaves_a_live_offer_on_an_owned_stl(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-034's known race, closed by the (user, product) advisory lock (ADR-037). The
    submission has read "not owned" when the payment reaches its auto-close."""
    user = await create_user(db_session)
    product = await stl(db_session)
    _, payment = await seed_order_with_attempt(db_session, user_id=user.id, product_id=product)
    barrier = asyncio.Barrier(2)
    real_owns, real_settle = OrderingStlOwnership.owns, _SETTLE_REAL

    async def submission_side(self: OrderingStlOwnership, *args: Any) -> bool:
        owned = await real_owns(self, *args)
        await meet_or_fail(barrier)
        await asyncio.sleep(STAGGER)  # the payment reaches its auto-close meanwhile
        return owned

    async def payment_side(*args: Any, **kwargs: Any) -> None:
        await meet_or_fail(barrier)
        await real_settle(*args, **kwargs)

    monkeypatch.setattr(OrderingStlOwnership, "owns", submission_side)
    monkeypatch.setattr(ordering_side, "settle_offers_on_stl_purchase", payment_side)
    client = await _client(app, user.email)
    body = {"product_id": str(product), "amount_cents": 800, "currency": "USD"}
    try:
        submitted, outcome = await asyncio.gather(
            client.post(OFFERS, json=body, headers=_csrf(client, False)), pay(db_engine, payment)
        )
    finally:
        await client.aclose()
    assert outcome is Outcome.APPLY_PAID
    assert submitted.status_code == 201, submitted.text
    state = await offer_state(db_engine, uuid.UUID(submitted.json()["id"]))
    assert state["status"] == "auto_closed", state["rounds"]


async def test_an_accept_racing_a_cart_payment_ends_auto_closed(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept holds the offer row and has read "not owned"; the payment waits for that row."""
    user = await create_user(db_session)
    product = await stl(db_session)
    offer = await seed_offer(
        db_session, user_id=user.id, product_id=product, status="awaiting_customer"
    )
    _, payment = await seed_order_with_attempt(db_session, user_id=user.id, product_id=product)
    barrier = asyncio.Barrier(2)
    real_owns, real_settle = OrderingStlOwnership.owns, _SETTLE_REAL

    async def accept_side(self: OrderingStlOwnership, *args: Any) -> bool:
        owned = await real_owns(self, *args)
        await meet_or_fail(barrier)
        await asyncio.sleep(STAGGER)
        return owned

    async def payment_side(*args: Any, **kwargs: Any) -> None:
        await meet_or_fail(barrier)
        await real_settle(*args, **kwargs)

    monkeypatch.setattr(OrderingStlOwnership, "owns", accept_side)
    monkeypatch.setattr(ordering_side, "settle_offers_on_stl_purchase", payment_side)
    client = await _client(app, user.email)
    try:
        accepted, outcome = await asyncio.gather(
            client.post(
                f"/api/v1/me/offers/{offer}/accept",
                json={"expected_amount_cents": 800},
                headers=_csrf(client, False),
            ),
            pay(db_engine, payment),
        )
    finally:
        await client.aclose()
    assert (accepted.status_code, outcome) == (200, Outcome.APPLY_PAID), accepted.text
    assert (await offer_state(db_engine, offer))["status"] == "auto_closed"


async def test_an_offer_checkout_racing_a_cart_payment_of_the_same_stl_does_not_deadlock(
    app: FastAPI, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The payment holds the line it moved and wants the offer; offer checkout inserts its
    line before it locks the offer, so it only waits on the payment, never the reverse."""
    user, product, offer = await _accepted(db_session)
    _, payment = await seed_order_with_attempt(db_session, user_id=user.id, product_id=product)
    barrier = asyncio.Barrier(2)
    real_settle, real_insert = (
        _SETTLE_REAL,
        SqlOrderStore.insert_lines,
    )

    async def payment_side(*args: Any, **kwargs: Any) -> None:
        await meet_or_fail(barrier)
        await asyncio.sleep(STAGGER)  # offer checkout is now waiting on the moved line
        await real_settle(*args, **kwargs)

    async def checkout_side(self: SqlOrderStore, *args: Any, **kwargs: Any) -> Any:
        await meet_or_fail(barrier)
        return await real_insert(self, *args, **kwargs)

    monkeypatch.setattr(ordering_side, "settle_offers_on_stl_purchase", payment_side)
    monkeypatch.setattr(SqlOrderStore, "insert_lines", checkout_side)
    client = await _client(app, user.email)
    try:
        response, outcome = await asyncio.gather(
            _offer_checkout(client, offer), pay(db_engine, payment)
        )
    finally:
        await client.aclose()
    assert outcome is Outcome.APPLY_PAID
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "PRODUCT_ALREADY_OWNED"
    assert (await offer_state(db_engine, offer))["status"] == "auto_closed"
