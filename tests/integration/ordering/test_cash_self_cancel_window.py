"""ADR-038 d23 (VS-031 must-resolve 1): a cash order the customer cancelled themselves counts
toward `cash_max_open_orders` for 24 hours, for that customer and for that phone, so a
prober cannot place, cancel and probe again. Real checkouts; the window at -1 s, 0, +1 s."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
import time_machine
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.cancel_support import admin_cancel, customer_cancel
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    post,
    random_phone,
    setting,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

WINDOW = timedelta(hours=24)
T0 = datetime(2031, 3, 1, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


def _cash(client: TestClient, product_id: uuid.UUID, phone: str) -> Any:
    add_to_cart(client, product_id)
    return post(client, pickup_body(phone))


def _place_and_self_cancel(client: TestClient, product_id: uuid.UUID, phone: str) -> uuid.UUID:
    placed = _cash(client, product_id, phone)
    assert placed.status_code == 201, placed.text
    order_id = uuid.UUID(placed.json()["order"]["id"])
    cancelled = customer_cancel(client, order_id)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    return order_id


async def test_place_self_cancel_and_probe_again_is_refused_for_the_customer_and_the_phone(
    db_session: AsyncSession,
) -> None:
    lamp, phone = await physical(db_session), random_phone()
    prober, other = await create_user(db_session), await create_user(db_session)
    with client_for(main_app) as client:
        login(client, prober.email)
        _place_and_self_cancel(client, lamp, phone)
        same_phone = _cash(client, lamp, phone)
        other_phone = _cash(client, lamp, random_phone())
    assert_problem(same_phone, 422, "CASH_NOT_AVAILABLE")
    assert_problem(other_phone, 422, "CASH_NOT_AVAILABLE")
    with client_for(main_app) as client:
        login(client, other.email)
        by_phone = _cash(client, lamp, phone)
        elsewhere = _cash(client, lamp, random_phone())
    assert_problem(by_phone, 422, "CASH_NOT_AVAILABLE")
    assert "reason" not in by_phone.json()
    assert elsewhere.status_code == 201, elsewhere.text


@pytest.mark.parametrize(("offset", "allowed"), [(-1, False), (0, True), (1, True)])
async def test_the_window_ends_exactly_24_hours_after_the_cancel(
    offset: int, allowed: bool, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp, phone, prober = await physical(db_session), random_phone(), await create_user(db_session)
    with client_for(main_app) as client:
        login(client, prober.email)
        order_id = _place_and_self_cancel(client, lamp, phone)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE orders SET customer_cancelled_at = :t WHERE id = :o"),
            {"t": T0, "o": order_id},
        )
    with time_machine.travel(T0 + WINDOW + timedelta(seconds=offset), tick=False):
        # Each probe on one dimension only: an allowed one places an order of its own.
        with client_for(main_app) as client:
            login(client, (await create_user(db_session)).email)
            probes = [_cash(client, lamp, phone)]  # another account, the same phone
        with client_for(main_app) as client:
            login(client, prober.email)
            probes.append(_cash(client, lamp, random_phone()))  # the customer, another phone
    for probe in probes:
        if allowed:
            assert probe.status_code == 201, probe.text
        else:
            assert_problem(probe, 422, "CASH_NOT_AVAILABLE")


async def test_a_raised_limit_counts_the_self_cancelled_order_as_one(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp, phone, prober = await physical(db_session), random_phone(), await create_user(db_session)
    async with setting(db_engine, "cash_max_open_orders", 2):
        with client_for(main_app) as client:
            login(client, prober.email)
            _place_and_self_cancel(client, lamp, phone)
            second = _cash(client, lamp, phone)
            third = _cash(client, lamp, phone)
    assert second.status_code == 201, second.text
    assert_problem(third, 422, "CASH_NOT_AVAILABLE")


async def test_an_admin_cancel_and_an_online_self_cancel_do_not_count(
    db_session: AsyncSession,
) -> None:
    """Only the customer's own cancel of a cash order is the probe (ADR-038 d23)."""
    lamp, phone, buyer = await physical(db_session), random_phone(), await create_user(db_session)
    with client_for(main_app) as client:
        login(client, buyer.email)
        placed = _cash(client, lamp, phone)
    assert placed.status_code == 201, placed.text
    order_id = uuid.UUID(placed.json()["order"]["id"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert admin_cancel(client, order_id).status_code == 200
    online = await seed_physical_order(
        db_session, user_id=buyer.id, payment_method="online", payment_status="paid"
    )
    with client_for(main_app) as client:
        login(client, buyer.email)
        assert customer_cancel(client, online.order_id).status_code == 200
        again = _cash(client, lamp, phone)
    assert again.status_code == 201, again.text
