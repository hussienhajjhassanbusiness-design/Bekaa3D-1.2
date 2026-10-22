"""VS-028 end to end (plan 6.6): a new customer registers, verifies and checks out physical
goods, once as cash at pickup and once as a mixed delivery order paid through the mock."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.jobs.verify_payments import verify_payments
from app.main import app as main_app
from app.ordering.domain.fulfillment import DELIVERY_FEE_NOTE
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.e2e.test_vs023_digital_purchase import _verification_token
from tests.integration.catalog.storefront_support import seed_refs
from tests.integration.deep_support import PASSWORD, client_for, csrf, login
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    checkout_body,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    post,
    random_phone,
    setting,
    spaced,
    stl,
    usd,
)
from tests.integration.payments.verification_support import (
    WEBHOOK,
    mock_fixture,  # noqa: F401
    signed,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


async def _new_customer(client: TestClient, db: AsyncSession) -> str:
    email = f"e2e-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
    )
    assert registered.status_code == 202, registered.text
    token = await _verification_token(db, email)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
    login(client, email)
    return email


async def test_a_new_customer_places_a_cash_pickup_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session, price_cents=1800)
    with client_for(main_app) as client:
        email = await _new_customer(client, db_session)
        add_to_cart(client, lamp, 2)
        placed = post(client, pickup_body(spaced(random_phone())))
        assert placed.status_code == 201, placed.text
        order = placed.json()["order"]
        detail = client.get(f"/api/v1/me/orders/{order['id']}").json()
        listed = client.get("/api/v1/me/orders").json()["items"]
        cart = client.get("/api/v1/cart").json()
    assert placed.json()["payment"] is None
    assert (order["status"], order["payment_method"], order["fulfillment_method"]) == (
        "in_progress",
        "cash",
        "pickup",
    )
    assert order["payment_due"] is True
    assert order["amount_due"] == order["total"] == usd(3600)
    assert (detail["payment_due"], detail["amount_due"], detail["payment"]) == (
        True,
        usd(3600),
        None,
    )
    assert [(row["id"], row["amount_due"]) for row in listed] == [(order["id"], usd(3600))]
    assert cart["items"] == []
    async with db_engine.connect() as conn:
        payload = await conn.scalar(
            text(
                "SELECT payload FROM email_outbox WHERE template = 'order_cash_placed'"
                " AND recipient_email = :e"
            ),
            {"e": email},
        )
    assert (payload["amount_due_cents"], payload["currency"], payload["pickup"]) == (
        3600,
        "USD",
        True,
    )


async def test_a_new_customer_pays_a_mixed_delivery_order_online(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The webhook's background task is dropped, so the cron is what applies the payment."""

    async def dropped(*args: Any) -> None:
        return None

    monkeypatch.setattr("app.payments.api.webhooks.verify_in_background", dropped)
    refs = await seed_refs(db_session)
    lamp, file = await physical(db_session, refs), await stl(db_session, refs)
    with client_for(main_app) as client:
        await _new_customer(client, db_session)
        address = client.post(
            "/api/v1/me/addresses",
            json={
                "label": "Home",
                "recipient_name": "Rita Customer",
                "phone": "71 123 456",
                "governorate": "beirut",
                "city": "Beirut",
                "landmark_notes": "Blue door",
            },
            headers=csrf(client),
        )
        assert address.status_code == 201, address.text
        add_to_cart(client, lamp)
        add_to_cart(client, file)
        placed = post(
            client,
            checkout_body(fulfillment_method="delivery", address_id=address.json()["id"]),
        )
        assert placed.status_code == 201, placed.text
        order, payment_id = placed.json()["order"], placed.json()["payment"]["id"]
        assert (order["status"], order["payment_due"], order["amount_due"]) == (
            "pending_payment",
            False,
            None,
        )
        await mock.simulate(uuid.UUID(payment_id), "paid")
        raw = json.dumps(
            {
                "event_id": f"ev_e2e_{uuid.uuid4().hex}",
                "type": "payment",
                "payment_reference": payment_id,
            }
        ).encode()
        assert client.post(WEBHOOK, content=raw, headers=signed(raw)).status_code == 200
        await verify_payments(
            {
                "session_factory": async_sessionmaker(db_engine, expire_on_commit=False),
                "payment_providers": {"mock": mock},
            }
        )
        detail = client.get(f"/api/v1/me/orders/{order['id']}").json()
    lines = {line["product_type"]: line["fulfillment_status"] for line in detail["lines"]}
    assert detail["status"] == "in_progress"
    assert lines == {"physical": "pending", "stl": "awaiting_delivery"}
    assert detail["payment"]["status"] == "paid"
    assert detail["estimated_dispatch_at"] == order["estimated_dispatch_at"] is not None
    assert detail["delivery_fee_note"] == DELIVERY_FEE_NOTE
    assert detail["delivery_address"]["recipient_name"] == "Rita Customer"
