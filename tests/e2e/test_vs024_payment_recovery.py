"""VS-024 end to end (plan 6.6): a failed payment retried and paid; an expired one released
by the job and the STL bought again; a no-status provider's order released by an admin
after the hold and the grace. Time moves by backdating rows or the job's `now`."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.jobs.verify_payments import verify_payments
from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_stale
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.e2e.test_vs023_digital_purchase import _verification_token
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, client_for, create_user, csrf, login, mfa_admin
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    post_checkout,
    shop_open,  # noqa: F401
)
from tests.integration.payments.recovery_support import HOLD, ORDER_STATE, keyset_start, one
from tests.integration.payments.test_verification_recovery import NoStatus
from tests.integration.payments.verification_support import (
    WEBHOOK,
    mock_fixture,  # noqa: F401
    signed,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]

GRACE = timedelta(hours=24)
NO_STATUS: Any = {"mock": NoStatus()}


class QuietNoStatus(NoStatus):
    async def aclose(self) -> None:
        return None


def _webhook(client: TestClient, payment_id: str) -> None:
    body = json.dumps(
        {
            "event_id": f"ev_e2e_{uuid.uuid4().hex}",
            "type": "payment.updated",
            "payment_reference": payment_id,
        }
    ).encode()
    assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200


async def _cron(engine: AsyncEngine, mock: MockPaymentProvider) -> None:
    await verify_payments(
        {
            "session_factory": async_sessionmaker(engine, expire_on_commit=False),
            "payment_providers": {"mock": mock},
        }
    )


async def _stl(db: AsyncSession) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db), type=ProductType.STL, price_cents=1250)).id


async def test_a_failed_payment_is_retried_and_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """register -> checkout -> mock_pay failed -> retry -> mock_pay paid -> awaiting delivery."""
    stl = await _stl(db_session)
    email = f"e2e-retry-{uuid.uuid4().hex}@example.com"
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
        order_id, first = placed.json()["order"]["id"], placed.json()["payment"]["id"]

        await mock.simulate(uuid.UUID(first), "failed")
        _webhook(client, first)
        await _cron(engine=db_engine, mock=mock)
        retried = client.post(
            f"/api/v1/me/orders/{order_id}/payments",
            json={},
            headers=csrf(client) | {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"},
        )
        assert retried.status_code == 201, retried.text
        second = retried.json()["payment"]["id"]
        assert second != first and retried.json()["order"]["id"] == order_id

        await mock.simulate(uuid.UUID(second), "paid")
        _webhook(client, second)
        await _cron(engine=db_engine, mock=mock)
        owned = client.get("/api/v1/me/stl-ownership", params={"product_id": str(stl)}).json()
    state = await one(db_engine, ORDER_STATE, o=uuid.UUID(order_id))
    assert (state.status, state.lines, owned["owned"]) == (
        "in_progress",
        ["awaiting_delivery"],
        True,
    )
    async with db_engine.connect() as conn:
        statuses: Any = (
            await conn.execute(
                text("SELECT status FROM payments WHERE order_id = :o ORDER BY initiated_at"),
                {"o": order_id},
            )
        ).scalars()
        assert list(statuses) == ["failed", "paid"]


async def test_an_expired_payment_is_released_and_the_stl_bought_again(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """checkout -> mock_pay expired -> release job (clock past the hold) -> cancelled -> rebuy."""
    stl = await _stl(db_session)
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        add_to_cart(client, stl)
        placed = post_checkout(client)
        assert placed.status_code == 201, placed.text
        order_id = uuid.UUID(placed.json()["order"]["id"])
        await mock.simulate(uuid.UUID(placed.json()["payment"]["id"]), "expired")
        placed_at = datetime.fromisoformat(placed.json()["order"]["placed_at"])
        counts = await release_stale(
            async_sessionmaker(db_engine, expire_on_commit=False),
            {"mock": mock},
            now=placed_at + HOLD + timedelta(minutes=1),
            start_after=keyset_start(placed_at),
        )
        assert counts["released"] == 1, counts
        add_to_cart(client, stl)
        again = post_checkout(client)
    released = await one(db_engine, ORDER_STATE, o=order_id)
    assert (released.status, released.lines, released.notices, released.emails) == (
        "cancelled",
        ["cancelled"],
        1,
        1,
    )
    assert again.status_code == 201, again.text
    assert again.json()["order"]["id"] != str(order_id)


async def test_a_no_status_order_is_released_by_an_admin_after_the_grace(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """checkout (no-status provider) -> hold + grace -> the job never releases it -> an admin
    releases it with a reason -> cancelled."""
    stl = await _stl(db_session)
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        add_to_cart(client, stl)
        placed = post_checkout(client)
        assert placed.status_code == 201, placed.text
    order_id = uuid.UUID(placed.json()["order"]["id"])
    back = datetime.now(UTC) - HOLD - GRACE - timedelta(minutes=1)
    async with db_engine.begin() as conn:  # the hold and the grace have passed
        await conn.execute(
            text("UPDATE orders SET placed_at = :t WHERE id = :o"), {"t": back, "o": order_id}
        )
        await conn.execute(
            text("UPDATE payments SET initiated_at = :t WHERE order_id = :o"),
            {"t": back, "o": order_id},
        )
    counts = await release_stale(
        async_sessionmaker(db_engine, expire_on_commit=False),
        NO_STATUS,
        now=datetime.now(UTC),
        start_after=keyset_start(back),
    )
    assert counts["released"] == 0, counts
    assert (await one(db_engine, ORDER_STATE, o=order_id)).status == "pending_payment"
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        detail = client.get("/api/v1/admin/payments", params={"order_id": str(order_id)}).json()[
            "items"
        ][0]
        actions = client.get(f"/api/v1/admin/payments/{detail['id']}").json()["available_actions"]
        released = client.post(
            f"/api/v1/admin/orders/{order_id}/release",
            json={"reason": "dashboard shows no payment; the customer never paid"},
            headers=csrf(client),
        )
    assert actions == ["confirm", "release_order"]
    assert released.status_code == 200, released.text
    state: Any = await one(db_engine, ORDER_STATE, o=order_id)
    assert (state.status, state.lines, state.released_audits) == ("cancelled", ["cancelled"], 1)
    assert admin.id is not None
