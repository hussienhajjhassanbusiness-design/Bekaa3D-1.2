"""VS-031 end to end. The SRS 5.6 mandatory path: a mixed order is paid online, the printer
fails, the administrator cancels the physical line and its refund stays pending until
settled while the STL line is still sent. And a cash refusal that blocks cash."""

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
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.order_support import transition_path
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    checkout_body,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    post,
    random_phone,
    setting,
    spaced,
    stl,
)
from tests.integration.payments.refund_support import REFUNDS, act, ok, statuses
from tests.integration.payments.verification_support import (
    WEBHOOK,
    mock_fixture,  # noqa: F401
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]


@pytest_asyncio.fixture(autouse=True)
async def _pickup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


def _address(client: TestClient, phone: str) -> str:
    response = client.post(
        "/api/v1/me/addresses",
        json={
            "label": "Home",
            "recipient_name": "Rita Customer",
            "phone": phone,
            "governorate": "beirut",
            "city": "Beirut",
            "landmark_notes": "Blue door",
        },
        headers=csrf(client),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _move(client: TestClient, order_id: str, line_id: str, target: str, **extra: Any) -> Any:
    response = client.post(
        transition_path(uuid.UUID(order_id), uuid.UUID(line_id)),
        json={"target_status": target} | extra,
        headers=csrf(client),
    )
    return ok(response)


async def _pay(engine: AsyncEngine, mock: MockPaymentProvider, payment_id: str) -> None:
    await mock.simulate(uuid.UUID(payment_id), "paid")
    raw = json.dumps(
        {"event_id": f"ev_{uuid.uuid4().hex}", "type": "payment", "payment_reference": payment_id}
    ).encode()
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=raw, headers=signed(raw)).status_code == 200
    await verify_payments(
        {
            "session_factory": async_sessionmaker(engine, expire_on_commit=False),
            "payment_providers": {"mock": mock},
        }
    )


async def test_srs_5_6_a_mixed_order_partly_refunded_by_cancelling_its_physical_line(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    lamp, model = await physical(db_session, price_cents=1200), await stl(db_session)
    with client_for(main_app) as client:
        email = await _new_customer(client, db_session)
        add_to_cart(client, lamp)
        add_to_cart(client, model)
        address = _address(client, spaced(random_phone()))
        body = checkout_body(fulfillment_method="delivery", address_id=address)
        placed = post(client, body)
        assert placed.status_code == 201, placed.text
        order, payment_id = placed.json()["order"], placed.json()["payment"]["id"]
    await _pay(db_engine, mock, payment_id)
    lines = {line["product_type"]: line["id"] for line in order["lines"]}
    order_id = uuid.UUID(order["id"])
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        _move(admin, order["id"], lines["physical"], "in_production")
        cancelled = _move(admin, order["id"], lines["physical"], "cancelled", reason="Printer")
        by_type = {line["product_type"]: line for line in cancelled["lines"]}
        assert by_type["physical"]["fulfillment_status"] == "cancelled"
        assert by_type["stl"]["fulfillment_status"] == "awaiting_delivery"
        assert cancelled["status"] == "partially_refunded"
        queue = ok(admin.get(REFUNDS, params={"order_id": order["id"]}))["items"]
        [refund] = queue
        assert (refund["kind"], refund["status"], refund["amount_cents"]) == (
            "cancellation",
            "pending",
            1200,
        )
        sent = _move(admin, order["id"], lines["stl"], "delivered")
        assert sent["status"] == "partially_refunded"
        ok(act(admin, refund["id"], "settle", {"reference": "dash-5.6"}))
        assert ok(admin.get(REFUNDS, params={"order_id": order["id"]}))["items"] == []
    assert await statuses(db_engine, order_id) == ("partially_refunded", "partially_refunded")
    with client_for(main_app) as client:
        login(client, email, PASSWORD)
        seen = ok(client.get(f"/api/v1/me/orders/{order['id']}"))
    assert seen["status"] == "partially_refunded"
    assert [(r["kind"], r["status"]) for r in seen["refunds"]] == [("cancellation", "refunded")]


async def test_a_refused_cash_delivery_is_cancelled_unrefunded_and_blocks_cash(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp, phone = await physical(db_session), spaced(random_phone())  # its own: A-03
    with client_for(main_app) as client:
        await _new_customer(client, db_session)
        add_to_cart(client, lamp)
        cash = checkout_body(payment_method="cash", accept_cash_terms=True)
        placed = post(
            client, cash | {"fulfillment_method": "delivery", "address_id": _address(client, phone)}
        )
        assert placed.status_code == 201, placed.text
        order = placed.json()["order"]
    line = order["lines"][0]["id"]
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        for step in ("in_production", "ready_to_ship", "shipped", "returned"):
            _move(admin, order["id"], line, step)
        done = _move(admin, order["id"], line, "cancelled", cancel_reason="refused")
        assert (done["status"], done["payments"]) == ("cancelled", [])
        assert ok(admin.get(REFUNDS, params={"order_id": order["id"]}))["items"] == []
        blocks = ok(admin.get("/api/v1/admin/cash-blocks", params={"active": "true"}))["items"]
        assert order["id"] in [b["order_id"] for b in blocks]
    with client_for(main_app) as client:
        await _new_customer(client, db_session)  # another account, the same phone
        add_to_cart(client, lamp)
        again = post(
            client, cash | {"fulfillment_method": "delivery", "address_id": _address(client, phone)}
        )
        online = post(
            client, checkout_body(fulfillment_method="delivery", address_id=_address(client, phone))
        )
    assert_problem(again, 422, "CASH_NOT_AVAILABLE")
    assert online.status_code == 201, online.text
