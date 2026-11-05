"""VS-023b end to end: register, buy through the mock, let `verify_payments` apply it, then
the administrator works the queue. Clients open one after the other; `dispatch_outbox` sends
the email last, so the provider sees nothing before it runs."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.integrations.email.console import ConsoleEmailProvider
from app.jobs.outbox import dispatch_outbox
from app.jobs.verify_payments import verify_payments
from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.platform.infrastructure.models import EmailOutboxModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, client_for, login, mfa_admin
from tests.integration.fulfillment.delivery_support import QUEUE, transition_path
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    post_checkout,
    shop_open,  # noqa: F401
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


async def _verification_token(db: AsyncSession, email: str) -> str:
    db.expire_all()
    outbox = await db.scalar(
        select(EmailOutboxModel)
        .where(EmailOutboxModel.recipient_email == email)
        .order_by(EmailOutboxModel.created_at.desc())
        .limit(1)
    )
    assert outbox is not None
    return str(outbox.payload["token"])


async def _dropped(*args: Any) -> None:
    return None


async def _register(customer: TestClient, db: AsyncSession) -> str:
    email = f"e2e23b-{uuid.uuid4().hex}@example.com"
    registered = customer.post(
        "/api/v1/auth/register",
        json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
    )
    assert registered.status_code == 202, registered.text
    token = await _verification_token(db, email)
    assert customer.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
    login(customer, email)
    return email


async def _buy(
    customer: TestClient,
    products: list[uuid.UUID],
    db_engine: AsyncEngine,
    mock: MockPaymentProvider,
) -> dict[str, Any]:
    """Checkout, the mock's `paid`, then the real verification job. Returns the order."""
    for product in products:
        add_to_cart(customer, product)
    placed = post_checkout(customer)
    assert placed.status_code == 201, placed.text
    order, payment = placed.json()["order"], placed.json()["payment"]
    await mock.simulate(uuid.UUID(payment["id"]), "paid")
    body = json.dumps(
        {
            "event_id": f"ev_e2e_{uuid.uuid4().hex}",
            "type": "payment.updated",
            "payment_reference": payment["id"],
        }
    ).encode()
    assert customer.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    await verify_payments(
        {
            "session_factory": async_sessionmaker(db_engine, expire_on_commit=False),
            "payment_providers": {"mock": mock},
        }
    )
    found: dict[str, Any] = order
    return found


async def _user_id(db: AsyncSession, email: str) -> uuid.UUID:
    found = await db.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    assert found is not None
    return uuid.UUID(str(found))


def _stl_emails(send: AsyncMock, email: str) -> list[dict[str, Any]]:
    return [
        dict(call.kwargs)
        for call in send.await_args_list
        if call.kwargs["template"] == "order_stl_delivered" and call.kwargs["to"] == email
    ]


async def test_register_buy_queue_mark_sent_customer_notified(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.payments.api.webhooks.verify_in_background", _dropped)
    # On the class, so a send from anywhere is seen, not only the job's.
    send = AsyncMock()
    monkeypatch.setattr(ConsoleEmailProvider, "send", send)
    stl = (
        await seed_product(
            db_session, await seed_refs(db_session), type=ProductType.STL, price_cents=1250
        )
    ).id
    with client_for(main_app) as customer:
        email = await _register(customer, db_session)
        order = await _buy(customer, [stl], db_engine, mock)
        owed = customer.get(f"/api/v1/me/orders/{order['id']}").json()["lines"][0]
        assert (owed["fulfillment_status"], owed["fulfilled_at"]) == ("awaiting_delivery", None)
    customer_id = await _user_id(db_session, email)

    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        (row,) = admin.get(QUEUE, params={"customer_id": str(customer_id)}).json()["items"]
        assert (row["order_id"], row["customer_email"]) == (order["id"], email)
        done = admin.post(
            transition_path(uuid.UUID(row["order_id"]), uuid.UUID(row["item_id"])),
            json={"target_status": "delivered"},
            headers={"X-CSRF-Token": admin.cookies["csrf_token"]},
        )
        assert done.status_code == 200, done.text
        empty = admin.get(QUEUE, params={"customer_id": str(customer_id)}).json()

    with client_for(main_app) as customer:
        login(customer, email)
        detail = customer.get(f"/api/v1/me/orders/{order['id']}").json()

    assert empty["items"] == []
    assert detail["status"] == "completed"
    sent = detail["lines"][0]
    assert sent["fulfillment_status"] == "delivered" and sent["fulfilled_at"] is not None
    async with db_engine.connect() as conn:
        notes = await conn.scalar(
            text(
                "SELECT count(*) FROM notifications WHERE user_id = :u"
                " AND payload->>'event' = 'stl.delivered'"
            ),
            {"u": customer_id},
        )
    assert notes == 1

    assert _stl_emails(send, email) == [], "nothing is sent before the job runs"
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    while await dispatch_outbox({"session_factory": factory}):
        pass
    assert _stl_emails(send, email) == [
        {
            "to": email,
            "template": "order_stl_delivered",
            "payload": {
                "order_id": order["id"],
                "order_number": row["order_number"],
                "item_id": row["item_id"],
                "product_name": row["product_name"],
            },
        }
    ]


async def test_two_stls_of_one_checkout_share_a_moment_and_paging_hides_neither(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A-01: one checkout writes one `created_at`, so ties are the normal case for the keyset.
    Comparing on the time alone would drop the second paid line from the next page."""
    monkeypatch.setattr("app.payments.api.webhooks.verify_in_background", _dropped)
    refs = await seed_refs(db_session)
    stls = [
        (await seed_product(db_session, refs, type=ProductType.STL, price_cents=cents)).id
        for cents in (500, 700)
    ]
    with client_for(main_app) as customer:
        email = await _register(customer, db_session)
        order = await _buy(customer, stls, db_engine, mock)
    async with db_engine.connect() as conn:
        lines = (
            await conn.execute(
                text(
                    "SELECT id, created_at, fulfillment_status FROM order_items WHERE order_id = :o"
                ),
                {"o": uuid.UUID(order["id"])},
            )
        ).all()
    assert {line.fulfillment_status for line in lines} == {"awaiting_delivery"}
    assert len(lines) == 2 and len({line.created_at for line in lines}) == 1

    params: dict[str, Any] = {"customer_id": str(await _user_id(db_session, email)), "limit": 1}
    seen: list[str] = []
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        for _ in range(3):
            page = admin.get(QUEUE, params=params).json()
            assert len(page["items"]) == 1
            seen.append(page["items"][0]["item_id"])
            if page["next_cursor"] is None:
                break
            params["cursor"] = page["next_cursor"]
    assert seen == sorted(str(line.id) for line in lines)
