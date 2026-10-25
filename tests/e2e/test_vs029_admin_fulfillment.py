"""VS-029 end to end: a customer's physical order is checked out for real, then the
administrator moves it to the end, once as cash at pickup through the handover and once as a
delivery paid online through the mock."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.verify_payments import verify_payments
from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.e2e.test_vs028_physical_checkout import _new_customer
from tests.integration.deep_support import PASSWORD, client_for, csrf, login, mfa_admin
from tests.integration.fulfillment.order_support import emails, handover_path, transition_path
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
PICKUP_ADDRESS = "Workshop, Zahle"


@pytest_asyncio.fixture(autouse=True)
async def _pickup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with (
        setting(db_engine, "pickup_address", PICKUP_ADDRESS),
        setting(db_engine, "pickup_hours", "Mon-Sat 9-17"),
    ):
        yield


def _move(client: TestClient, order_id: str, line_id: str, target: str) -> dict[str, Any]:
    response = client.post(
        transition_path(uuid.UUID(order_id), uuid.UUID(line_id)),
        json={"target_status": target},
        headers=csrf(client),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_a_cash_pickup_order_is_printed_handed_over_and_completed(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session, price_cents=1800)
    me: dict[str, Any] = {}
    with client_for(main_app) as client:
        email = await _new_customer(client, db_session)
        add_to_cart(client, lamp, 2)
        placed = post(client, pickup_body(random_phone()))
        assert placed.status_code == 201, placed.text
        order = placed.json()["order"]
        me["placed"] = client.get(f"/api/v1/me/orders/{order['id']}").json()
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        queue = admin.get("/api/v1/admin/orders", params={"payment_due": "true", "limit": 100})
        assert order["id"] in [item["id"] for item in queue.json()["items"]]
        [line] = admin.get(f"/api/v1/admin/orders/{order['id']}").json()["lines"]
        _move(admin, order["id"], line["id"], "in_production")
    with client_for(main_app) as client:
        login(client, email, PASSWORD)
        me["printing"] = client.get(f"/api/v1/me/orders/{order['id']}").json()
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        ready = _move(admin, order["id"], line["id"], "ready_for_pickup")
        assert [a["target_status"] for a in ready["lines"][0]["available_actions"]] == [
            "cancelled"  # VS-031: a refusal or no-show; the handover is its own route
        ]
        handed = admin.post(
            handover_path(uuid.UUID(order["id"])),
            json={"amount_cents": 3600, "currency": "USD"},
            headers=csrf(admin),
        )
    with client_for(main_app) as client:
        login(client, email, PASSWORD)
        me["done"] = client.get(f"/api/v1/me/orders/{order['id']}").json()
    assert me["placed"]["can_cancel"] is True and me["printing"]["can_cancel"] is False
    assert me["printing"]["lines"][0]["fulfillment_status"] == "pending"
    assert handed.status_code == 200, handed.text
    assert handed.json()["payments"][0]["amount"] == usd(3600)
    done = me["done"]
    assert (done["status"], done["payment_due"], done["payment"]["status"]) == (
        "completed",
        False,
        "paid",
    )
    assert done["lines"][0]["fulfillment_status"] == "picked_up"
    mails = await emails(db_engine, uuid.UUID(order["id"]))
    templates = [template for template, _ in mails]
    assert templates[-2:] == ["order_ready_for_pickup", "order_picked_up"]
    assert mails[-2][1]["pickup_address"] == PICKUP_ADDRESS
    assert mails[-1][1]["cash_receipt"]["amount_cents"] == 3600


async def test_a_delivery_order_paid_online_is_moved_to_delivered_and_completed(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        await _new_customer(client, db_session)
        address = client.post(
            "/api/v1/me/addresses",
            json={
                "label": "Home",
                "recipient_name": "Rita Customer",
                "phone": spaced(random_phone()),
                "governorate": "beirut",
                "city": "Beirut",
                "landmark_notes": "Blue door",
            },
            headers=csrf(client),
        )
        assert address.status_code == 201, address.text
        add_to_cart(client, lamp)
        placed = post(
            client, checkout_body(fulfillment_method="delivery", address_id=address.json()["id"])
        )
        assert placed.status_code == 201, placed.text
        order, payment_id = placed.json()["order"], placed.json()["payment"]["id"]
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        unpaid = admin.get(f"/api/v1/admin/orders/{order['id']}").json()
        hidden = admin.get("/api/v1/admin/orders", params={"order_number": order["order_number"]})
    assert unpaid["lines"][0]["available_actions"] == []
    assert hidden.json()["items"] == []
    await mock.simulate(uuid.UUID(payment_id), "paid")
    raw = json.dumps(
        {
            "event_id": f"ev_e2e_{uuid.uuid4().hex}",
            "type": "payment",
            "payment_reference": payment_id,
        }
    ).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=raw, headers=signed(raw)).status_code == 200
    await verify_payments(
        {
            "session_factory": async_sessionmaker(db_engine, expire_on_commit=False),
            "payment_providers": {"mock": mock},
        }
    )
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        line_id = admin.get(f"/api/v1/admin/orders/{order['id']}").json()["lines"][0]["id"]
        for step in ("in_production", "ready_to_ship", "shipped", "delivered"):
            final = _move(admin, order["id"], line_id, step)
    assert (final["status"], final["payment_reached_paid"]) == ("completed", True)
    mails = await emails(db_engine, uuid.UUID(order["id"]))
    steps = [t for t, _ in mails if t in {"order_ready", "order_shipped", "order_delivered"}]
    assert steps == ["order_ready", "order_shipped", "order_delivered"]
    assert all(payload["delivery_fee_note"] for t, payload in mails if t in steps)
