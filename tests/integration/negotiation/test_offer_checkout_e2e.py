"""SRS 5.4 end to end through the real routes (VS-041): offer, counter, accept, a later price
change, offer checkout, the provider's signed webhook and verification, then `paid`."""

import json
import uuid
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, csrf, login, mfa_admin
from tests.integration.negotiation.offer_support import (
    act,
    offer_state,
    shop_open,  # noqa: F401
    stl,
    submit,
)
from tests.integration.ordering.checkout_support import new_key, set_price
from tests.integration.payments.verification_support import (
    WEBHOOK,
    mock_fixture,  # noqa: F401
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]


def _as(email: str, call: Callable[[TestClient], httpx.Response]) -> httpx.Response:
    """One client at a time: a client's lifespan rebinds the app's engine to its loop."""
    with client_for(main_app) as client:
        login(client, email)
        return call(client)


async def test_negotiate_accept_pay_and_close_the_offer_as_paid(
    db_session: AsyncSession, db_engine: AsyncEngine, mock: MockPaymentProvider
) -> None:
    customer = await create_user(db_session)
    product = await stl(db_session, price_cents=1000)
    offer = uuid.UUID(_as(customer.email, lambda c: submit(c, product, 700)).json()["id"])
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        countered = act(
            admin, offer, "counter", {"amount_cents": 850, "currency": "USD"}, admin=True
        )
    assert countered.status_code == 200, countered.text
    accepted = _as(
        customer.email, lambda c: act(c, offer, "accept", {"expected_amount_cents": 850})
    )
    assert accepted.json()["agreed_amount"]["amount_cents"] == 850

    await set_price(db_session, product, 600)  # SRS 11.3: a later change is ignored
    url = f"/api/v1/me/offers/{offer}/checkout"
    body = {"accept_terms": True, "accept_digital_final_sale": True}
    placed = _as(
        customer.email,
        lambda c: c.post(url, json=body, headers=csrf(c) | {"Idempotency-Key": new_key()}),
    )
    assert placed.status_code == 201, placed.text
    order_id, payment_id = placed.json()["order"]["id"], placed.json()["payment"]["id"]
    assert placed.json()["order"]["total"]["amount_cents"] == 850

    await mock.simulate(uuid.UUID(payment_id), "paid")
    async with db_engine.connect() as conn:
        reference = await conn.scalar(
            text("SELECT provider_payment_id FROM payments WHERE id = :p"), {"p": payment_id}
        )
    event = {
        "event_id": f"ev_{uuid.uuid4().hex}",
        "type": "payment",
        "payment_reference": payment_id,
        "provider_payment_id": reference,
    }
    raw = json.dumps(event).encode()
    with client_for(main_app) as provider:
        assert provider.post(WEBHOOK, content=raw, headers=signed(raw)).status_code == 200

    state = await offer_state(db_engine, offer)
    assert state["status"] == "paid"
    assert [r.split(":", 1)[1] for r in state["rounds"]] == [
        "customer:submitted:700",
        "admin:countered:850",
        "customer:accepted:850",
        "system:paid:850",
    ]
    detail = _as(customer.email, lambda c: c.get(f"/api/v1/me/orders/{order_id}")).json()
    assert (detail["status"], detail["source"]) == ("in_progress", "offer")
    assert [line["fulfillment_status"] for line in detail["lines"]] == ["awaiting_delivery"]
    assert (detail["can_retry_payment"], detail["hold_expires_at"]) == (False, None)

    again = _as(
        customer.email,
        lambda c: c.post(url, json=body, headers=csrf(c) | {"Idempotency-Key": new_key()}),
    )
    assert (again.status_code, again.json()["offer_status"]) == (409, "paid")
