"""VS-023 end to end (plan 6.6): register, verify the email from the outbox, add an STL,
check out, pay through the mock, deliver a signed webhook, and let `verify_payments`
apply it; the line awaits delivery, ownership is true, email and notification exist."""

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
from tests.integration.deep_support import PASSWORD, client_for, login
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


async def test_a_customer_buys_an_stl_and_owns_it_once_the_payment_is_verified(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background task after the 200 is dropped, so the cron is what applies it."""

    async def dropped(*args: Any) -> None:
        return None

    monkeypatch.setattr("app.payments.api.webhooks.verify_in_background", dropped)
    stl = (
        await seed_product(
            db_session, await seed_refs(db_session), type=ProductType.STL, price_cents=1250
        )
    ).id
    email = f"e2e-{uuid.uuid4().hex}@example.com"
    with client_for(main_app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
        )
        assert registered.status_code == 202, registered.text
        token = await _verification_token(db_session, email)
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 204
        login(client, email)
        add_to_cart(client, stl)

        placed = post_checkout(client)
        assert placed.status_code == 201, placed.text
        order, payment = placed.json()["order"], placed.json()["payment"]
        assert (order["status"], order["total"]["amount_cents"]) == ("pending_payment", 1250)
        before = client.get("/api/v1/me/stl-ownership", params={"product_id": str(stl)}).json()

        await mock.simulate(uuid.UUID(payment["id"]), "paid")  # the customer pays the mock
        body = json.dumps(
            {
                "event_id": f"ev_e2e_{uuid.uuid4().hex}",
                "type": "payment.updated",
                "payment_reference": payment["id"],
            }
        ).encode()
        stored = client.post(WEBHOOK, content=body, headers=signed(body))
        assert stored.status_code == 200
        mid = client.get("/api/v1/me/stl-ownership", params={"product_id": str(stl)}).json()
        await verify_payments(
            {
                "session_factory": async_sessionmaker(db_engine, expire_on_commit=False),
                "payment_providers": {"mock": mock},
            }
        )
        after = client.get("/api/v1/me/stl-ownership", params={"product_id": str(stl)}).json()

    assert (before["owned"], mid["owned"], after["owned"]) == (False, False, True)
    async with db_engine.connect() as conn:
        state: Any = (
            await conn.execute(
                text(
                    "SELECT o.status, i.fulfillment_status, p.status AS payment_status,"
                    " p.verified_at IS NOT NULL AS verified,"
                    " (SELECT count(*) FROM email_outbox WHERE template = 'order_payment_confirmed'"
                    "   AND recipient_email = :e) AS emails,"
                    " (SELECT count(*) FROM notifications n JOIN users u ON u.id = n.user_id"
                    "   WHERE u.email = :e AND n.payload->>'event' = 'payment.confirmed') AS notes"
                    " FROM orders o JOIN order_items i ON i.order_id = o.id"
                    " JOIN payments p ON p.order_id = o.id WHERE o.id = :o"
                ),
                {"o": order["id"], "e": email},
            )
        ).one()
    assert (state.status, state.fulfillment_status) == ("in_progress", "awaiting_delivery")
    assert (state.payment_status, state.verified, state.emails, state.notes) == (
        "paid",
        True,
        1,
        1,
    )
