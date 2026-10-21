"""VS-023b end to end: register, buy an STL through the mock, let `verify_payments` apply
it, then the administrator finds the line in the queue and marks it sent; the customer sees
it delivered, with one notification and one email waiting in the outbox."""

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
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


async def test_register_buy_queue_mark_sent_customer_notified(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def dropped(*args: Any) -> None:
        return None

    monkeypatch.setattr("app.payments.api.webhooks.verify_in_background", dropped)
    stl = (
        await seed_product(
            db_session, await seed_refs(db_session), type=ProductType.STL, price_cents=1250
        )
    ).id
    email = f"e2e23b-{uuid.uuid4().hex}@example.com"
    with client_for(main_app) as customer:
        registered = customer.post(
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
        )
        assert registered.status_code == 202, registered.text
        token = await _verification_token(db_session, email)
        assert customer.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
        login(customer, email)
        add_to_cart(customer, stl)
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
        owed = customer.get(f"/api/v1/me/orders/{order['id']}").json()["lines"][0]
        assert (owed["fulfillment_status"], owed["fulfilled_at"]) == ("awaiting_delivery", None)
        customer_id = await _user_id(db_session, email)

        with client_for(main_app) as admin_client:
            await mfa_admin(admin_client, db_session)
            queue = admin_client.get(QUEUE, params={"customer_id": str(customer_id)}).json()
            (row,) = queue["items"]
            assert (row["order_id"], row["customer_email"]) == (order["id"], email)
            done = admin_client.post(
                transition_path(uuid.UUID(row["order_id"]), uuid.UUID(row["item_id"])),
                json={"target_status": "delivered"},
                headers={"X-CSRF-Token": admin_client.cookies["csrf_token"]},
            )
            assert done.status_code == 200, done.text
            empty = admin_client.get(QUEUE, params={"customer_id": str(customer_id)}).json()
        detail = customer.get(f"/api/v1/me/orders/{order['id']}").json()

    assert empty["items"] == []
    assert detail["status"] == "completed"
    sent = detail["lines"][0]
    assert sent["fulfillment_status"] == "delivered" and sent["fulfilled_at"] is not None
    async with db_engine.connect() as conn:
        counts: Any = (
            await conn.execute(
                text(
                    "SELECT"
                    " (SELECT count(*) FROM email_outbox WHERE template = 'order_stl_delivered'"
                    "   AND recipient_email = :e) AS emails,"
                    " (SELECT count(*) FROM notifications WHERE user_id = :u"
                    "   AND payload->>'event' = 'stl.delivered') AS notes"
                ),
                {"e": email, "u": customer_id},
            )
        ).one()
    assert (counts.emails, counts.notes) == (1, 1)


async def _user_id(db: AsyncSession, email: str) -> uuid.UUID:
    found = await db.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    assert found is not None
    return uuid.UUID(str(found))
