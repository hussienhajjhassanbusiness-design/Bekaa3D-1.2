"""`POST /api/v1/me/offers/{id}/checkout` (VS-041, F-094, BR-085, BR-086; ADR-037): the
agreed price, the window at its boundary, every refusal code, and that a refusal writes
nothing (no order, line, payment or claim; the offer untouched)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import time_machine
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.main import app as main_app
from app.payments.domain.exceptions import ProviderUnavailableError
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login
from tests.integration.negotiation.offer_support import offer_state, seed_offer, set_setting, stl
from tests.integration.ordering.checkout_support import (
    Rows,
    new_key,
    rows,
    set_price,
    shop_open,  # noqa: F401
)
from tests.integration.payments.support import seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]
BODY: dict[str, Any] = {"accept_terms": True, "accept_digital_final_sale": True}
NOTHING = Rows(orders=0, lines=0, payments=0, claims=0, cart_lines=0, history=0)
SECOND = timedelta(seconds=1)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


def checkout(
    client: TestClient,
    offer_id: uuid.UUID,
    body: dict[str, Any] | None = None,
    key: str | None = None,
) -> httpx.Response:
    headers = csrf(client) | {"Idempotency-Key": key or new_key()}
    response: httpx.Response = client.post(
        f"/api/v1/me/offers/{offer_id}/checkout",
        json=BODY if body is None else body,
        headers=headers,
    )
    return response


async def _accepted(
    client: TestClient, db: AsyncSession, **over: Any
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A signed-in customer's accepted offer: agreed 700 on a list price of 1000."""
    user = await create_user(db)
    login(client, user.email)
    product = await stl(db, price_cents=1000)
    fields: dict[str, Any] = {"agreed_amount_cents": 700, "responds_by": None}
    offer = await seed_offer(
        db, user_id=user.id, product_id=product, status="accepted", **(fields | over)
    )
    return user.id, product, offer


# ------------------------------------------------------------------- happy path


@pytest.mark.parametrize("list_price", [500, 1000, 2000])
async def test_checkout_charges_the_agreed_price_whatever_the_list_price(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, list_price: int
) -> None:
    user, product, offer = await _accepted(client, db_session)
    await set_price(db_session, product, list_price)
    response = checkout(client, offer)

    assert response.status_code == 201, response.text
    body = response.json()
    agreed = {"amount_cents": 700, "currency": "USD"}
    order = body["order"]
    assert (order["source"], order["status"], order["payment_method"]) == (
        "offer",
        "pending_payment",
        "online",
    )
    assert (order["subtotal"], order["total"]) == (agreed, agreed)
    [line] = order["lines"]
    assert (line["product_id"], line["unit_price"], line["quantity"]) == (str(product), agreed, 1)
    assert (body["payment"]["status"], body["dropped_lines"]) == ("pending", [])
    assert await rows(db_engine, user) == Rows(1, 1, 1, 1, 0, 1)
    async with db_engine.connect() as conn:
        stored = (
            await conn.execute(
                text(
                    "SELECT i.offer_id, p.amount_cents, o.digital_terms_version,"
                    " a.after_data->>'offer_id' AS audited"
                    " FROM order_items i JOIN payments p ON p.order_id = i.order_id"
                    " JOIN orders o ON o.id = i.order_id"
                    " JOIN audit_logs a ON a.entity_id = o.id AND a.action = 'order.placed'"
                    " WHERE i.user_id = :u"
                ),
                {"u": user},
            )
        ).one()
    assert (stored.offer_id, stored.amount_cents, stored.audited) == (offer, 700, str(offer))
    assert stored.digital_terms_version is not None
    # Paid, not checkout: the offer stays accepted until the payment is verified.
    assert (await offer_state(db_engine, offer))["status"] == "accepted"


async def test_the_same_key_replays_and_a_different_body_conflicts(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    key = new_key()
    first = checkout(client, offer, key=key)
    again = checkout(client, offer, key=key)
    other = checkout(client, offer, BODY | {"payment_provider": "mock"}, key=key)
    assert first.status_code == 201, first.text
    assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    assert_problem(other, 409, "IDEMPOTENCY_KEY_CONFLICT")
    assert (await rows(db_engine, user)).orders == 1


# ----------------------------------------------------------------- the window


@pytest.mark.parametrize(
    ("offset", "open_"), [(-SECOND, True), (0 * SECOND, False), (SECOND, False)]
)
async def test_the_window_closes_at_its_deadline(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    offset: timedelta,
    open_: bool,
) -> None:
    closes = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    user, _, offer = await _accepted(client, db_session, checkout_expires_at=closes)
    with time_machine.travel(closes + offset, tick=False):
        response = checkout(client, offer)
    if open_:
        assert response.status_code == 201, response.text
    else:
        assert_problem(response, 410, "OFFER_CHECKOUT_EXPIRED")
        assert await rows(db_engine, user) == NOTHING
        # A refusal writes nothing: the job, not the request, closes the offer.
        assert (await offer_state(db_engine, offer))["status"] == "accepted"


async def test_a_checkout_expired_offer_is_410(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE offers SET status = 'checkout_expired' WHERE id = :o"), {"o": offer}
        )
    assert_problem(checkout(client, offer), 410, "OFFER_CHECKOUT_EXPIRED")
    assert await rows(db_engine, user) == NOTHING


@pytest.mark.parametrize(
    "status",
    [
        "awaiting_admin",
        "awaiting_customer",
        "rejected",
        "expired",
        "withdrawn",
        "paid",
        "auto_closed",
    ],
)
async def test_an_offer_that_is_not_accepted_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, status: str
) -> None:
    user = await create_user(db_session)
    login(client, user.email)
    offer = await seed_offer(
        db_session, user_id=user.id, product_id=await stl(db_session), status=status
    )
    response = checkout(client, offer)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["offer_status"] == status
    assert await rows(db_engine, user.id) == NOTHING


async def test_another_customers_offer_and_an_unknown_one_are_404(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    owner = await create_user(db_session)
    offer = await seed_offer(
        db_session, user_id=owner.id, product_id=await stl(db_session), status="accepted"
    )
    intruder = await create_user(db_session)
    login(client, intruder.email)
    assert_problem(checkout(client, offer), 404)
    assert_problem(checkout(client, uuid.uuid4()), 404)
    assert await rows(db_engine, intruder.id) == NOTHING
    assert await rows(db_engine, owner.id) == NOTHING


# ------------------------------------------------------------- the shop paused


async def test_a_paused_shop_is_503_and_writes_nothing(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        response = checkout(client, offer)
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert_problem(response, 503, "ORDERS_PAUSED")
    assert await rows(db_engine, user) == NOTHING


async def test_a_window_lapsed_while_paused_is_410_not_503(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """ADR-037: the window does not stretch over a pause, and says so rather than "paused"."""
    lapsed = datetime.now(UTC) - SECOND
    _, _, offer = await _accepted(client, db_session, checkout_expires_at=lapsed)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        response = checkout(client, offer)
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert_problem(response, 410, "OFFER_CHECKOUT_EXPIRED")


async def test_no_online_provider_is_503_and_writes_nothing(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    get_settings.cache_clear()
    try:
        with client_for(main_app) as client:
            user, _, offer = await _accepted(client, db_session)
            response = checkout(client, offer)
    finally:
        get_settings.cache_clear()
    assert_problem(response, 503, "ONLINE_PAYMENT_UNAVAILABLE")
    assert await rows(db_engine, user) == NOTHING


# ----------------------------------------------------------- product and money


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [("is_visible", False, "not_listed"), ("is_available", False, "unavailable")],
)
async def test_a_hidden_or_unavailable_product_is_422(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    column: str,
    value: bool,
    reason: str,
) -> None:
    user, product, offer = await _accepted(client, db_session)
    async with db_engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE products SET {column} = :v WHERE id = :p"), {"v": value, "p": product}
        )
    response = checkout(client, offer)
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["lines"] == [{"product_id": str(product), "reason": reason}]
    assert await rows(db_engine, user) == NOTHING


async def test_a_second_checkout_while_a_payment_is_live_is_409_payment_already_active(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    first = checkout(client, offer)
    second = checkout(client, offer)
    assert first.status_code == 201, first.text
    assert_problem(second, 409, "PAYMENT_ALREADY_ACTIVE")
    body = second.json()
    assert (body["payment_id"], body["payment_status"]) == (
        first.json()["payment"]["id"],
        "pending",
    )
    assert body["redirect_url"] == first.json()["payment"]["redirect_url"]
    assert (await rows(db_engine, user)).orders == 1


async def test_a_second_checkout_after_a_failed_attempt_is_409_product_already_owned(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """The unpaid order still holds the line: the customer retries it instead (ADR-037)."""
    user, product, offer = await _accepted(client, db_session)
    first = checkout(client, offer)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE payments SET status = 'failed', failed_at = now() WHERE id = :p"),
            {"p": first.json()["payment"]["id"]},
        )
    response = checkout(client, offer)
    assert_problem(response, 409, "PRODUCT_ALREADY_OWNED")
    assert response.json()["product_ids"] == [str(product)]
    assert (await rows(db_engine, user)).orders == 1


async def test_an_stl_already_owned_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, product, offer = await _accepted(client, db_session)
    await seed_online_order(
        db_session, user_id=user, stl_id=product, line_status="awaiting_delivery"
    )
    response = checkout(client, offer)
    assert_problem(response, 409, "PRODUCT_ALREADY_OWNED")
    assert (await rows(db_engine, user)).orders == 1


async def test_a_provider_failure_is_502_keeps_the_order_and_replays(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    key = new_key()
    provider = main_app.state.payment_providers["mock"]

    async def down(request: object) -> object:
        raise ProviderUnavailableError("down")

    provider.create_payment = down
    try:
        failed = checkout(client, offer, key=key)
        replayed = checkout(client, offer, key=key)
    finally:
        del provider.create_payment
    assert_problem(failed, 502, "PAYMENT_PROVIDER_UNAVAILABLE")
    assert replayed.headers["Idempotent-Replayed"] == "true"
    counts = await rows(db_engine, user)
    assert (counts.orders, counts.payments) == (1, 1)


# --------------------------------------------------------------------- guards


@pytest.mark.parametrize(
    "body",
    [
        {"accept_terms": True},
        {"accept_terms": True, "accept_digital_final_sale": False},
        BODY | {"amount_cents": 1},
        BODY | {"payment_provider": ""},
    ],
)
async def test_a_bad_body_is_422_and_writes_nothing(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, body: dict[str, Any]
) -> None:
    user, _, offer = await _accepted(client, db_session)
    assert_problem(checkout(client, offer, body), 422, "VALIDATION_ERROR")
    assert await rows(db_engine, user) == NOTHING


async def test_an_unknown_provider_is_422_and_writes_nothing(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    response = checkout(client, offer, BODY | {"payment_provider": "whish"})
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert response.json()["reason"] == "provider_not_configured"
    assert await rows(db_engine, user) == NOTHING


async def test_the_session_boundary(client: TestClient, db_session: AsyncSession) -> None:
    owner = await create_user(db_session, verified=False)
    offer = await seed_offer(
        db_session, user_id=owner.id, product_id=await stl(db_session), status="accepted"
    )
    url = f"/api/v1/me/offers/{offer}/checkout"
    anonymous = client.post(url, json=BODY, headers={"Idempotency-Key": new_key()})
    login(client, owner.email)
    unverified = checkout(client, offer)
    assert_problem(anonymous, 401)
    assert_problem(unverified, 403, "EMAIL_VERIFICATION_REQUIRED")


async def test_without_csrf_or_a_key_nothing_is_written(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user, _, offer = await _accepted(client, db_session)
    url = f"/api/v1/me/offers/{offer}/checkout"
    no_csrf = client.post(url, json=BODY, headers={"Idempotency-Key": new_key()})
    no_key = client.post(url, json=BODY, headers=csrf(client))
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    assert_problem(no_key, 422)
    assert await rows(db_engine, user) == NOTHING
