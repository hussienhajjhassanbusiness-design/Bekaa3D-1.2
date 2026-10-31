"""Accepted payment methods at checkout (VS-049; BR-019, BR-141, ADR-048). Every refusal
asserts nothing was created and the cart is kept."""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_refs
from tests.integration.deep_support import assert_problem, client_for
from tests.integration.ordering.checkout_support import (
    checkout_body,
    new_key,
    rows,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    post,
    random_phone,
    setting,
    signed_in_buyer,
    stl,
)
from tests.integration.payments.support import seed_online_order
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

CART = "/api/v1/cart"
SPLIT = "These items can't be paid the same way; please order them separately."


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


def online_pickup() -> dict[str, Any]:
    return checkout_body(fulfillment_method="pickup", contact_phone=random_phone())


async def refused(
    client: TestClient, engine: AsyncEngine, user_id: uuid.UUID, body: dict[str, Any]
) -> Any:
    before = await rows(engine, user_id)
    response = post(client, body)
    assert await rows(engine, user_id) == before
    return response


async def line_snapshots(engine: AsyncEngine, order_id: str) -> dict[str, str | None]:
    sql = (
        "SELECT product_type::text, accepted_payment_methods_snapshot::text"
        " FROM order_items WHERE order_id = :o"
    )
    async with engine.connect() as conn:
        return dict((await conn.execute(text(sql), {"o": order_id})).tuples().all())


# ------------------------------------------------------------- no shared method


@pytest.mark.parametrize("chosen", ["online", "cash"])
async def test_a_cash_only_and_an_online_only_product_must_be_ordered_separately(
    db_engine: AsyncEngine, db_session: AsyncSession, chosen: str
) -> None:
    refs = await seed_refs(db_session)
    cash = await physical(db_session, refs, accepted_payment_methods="cash")
    online = await physical(db_session, refs, accepted_payment_methods="online")
    body = pickup_body(random_phone()) if chosen == "cash" else online_pickup()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, cash, online)
        response = await refused(client, db_engine, user_id, body)
    assert_problem(response, 422, "NO_COMMON_PAYMENT_METHOD")
    assert response.json()["detail"] == SPLIT
    assert response.json()["lines"] == [
        {"product_id": str(cash), "accepted_payment_methods": ["cash"]},
        {"product_id": str(online), "accepted_payment_methods": ["online"]},
    ]


@pytest.mark.parametrize("chosen", ["online", "cash"])
async def test_an_stl_beside_a_cash_only_product_has_no_shared_method(
    db_engine: AsyncEngine, db_session: AsyncSession, chosen: str
) -> None:
    refs = await seed_refs(db_session)
    cash, file = (
        await physical(db_session, refs, accepted_payment_methods="cash"),
        await stl(db_session, refs),
    )
    body = pickup_body(random_phone()) if chosen == "cash" else online_pickup()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, cash, file)
        response = await refused(client, db_engine, user_id, body)
    assert_problem(response, 422, "NO_COMMON_PAYMENT_METHOD")
    assert response.json()["lines"][1] == {
        "product_id": str(file),
        "accepted_payment_methods": ["online"],
    }


async def test_no_shared_method_comes_before_invalid_fulfillment_and_a_price_change(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-048 d4: the cart cannot be paid at all, whatever else is wrong with the request."""
    refs = await seed_refs(db_session)
    cash = await physical(db_session, refs, accepted_payment_methods="cash")
    online = await physical(db_session, refs, accepted_payment_methods="online")
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, cash, online)
        await db_session.execute(
            text("UPDATE products SET price_cents = 4321 WHERE id = :p"), {"p": cash}
        )
        await db_session.commit()
        response = await refused(client, db_engine, user_id, checkout_body())
    assert_problem(response, 422, "NO_COMMON_PAYMENT_METHOD")


# ------------------------------------------------------- one product refuses


@pytest.mark.parametrize(
    ("accepted", "chosen", "reason"),
    [("online", "cash", "cash_not_accepted"), ("cash", "online", "online_not_accepted")],
)
async def test_a_method_one_product_does_not_accept_names_that_product(
    db_engine: AsyncEngine, db_session: AsyncSession, accepted: str, chosen: str, reason: str
) -> None:
    refs = await seed_refs(db_session)
    both = await physical(db_session, refs)
    narrow = await physical(db_session, refs, accepted_payment_methods=accepted)
    body = pickup_body(random_phone()) if chosen == "cash" else online_pickup()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, both, narrow)
        response = await refused(client, db_engine, user_id, body)
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert (response.json()["reason"], response.json()["product_ids"]) == (reason, [str(narrow)])


async def test_cash_with_an_stl_keeps_its_reason_and_names_no_product(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp, file = await physical(db_session, refs), await stl(db_session, refs)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp, file)
        response = await refused(client, db_engine, user_id, pickup_body(random_phone()))
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert response.json()["reason"] == "cash_requires_physical"
    assert "product_ids" not in response.json()


# ------------------------------------------------------------- placed orders


@pytest.mark.parametrize(
    ("accepted", "chosen"),
    [("cash", "cash"), ("online", "online"), ("online_or_cash", "cash")],
)
async def test_an_accepted_method_places_the_order_and_snapshots_the_products_value(
    db_engine: AsyncEngine, db_session: AsyncSession, accepted: str, chosen: str
) -> None:
    lamp = await physical(db_session, accepted_payment_methods=accepted)
    body = pickup_body(random_phone()) if chosen == "cash" else online_pickup()
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, lamp)
        response = post(client, body)
    assert response.status_code == 201, response.text
    assert response.json()["order"]["payment_method"] == chosen
    snapshots = await line_snapshots(db_engine, response.json()["order"]["id"])
    assert snapshots == {"physical": accepted}


async def test_a_mixed_online_order_snapshots_only_its_physical_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp = await physical(db_session, refs, accepted_payment_methods="online")
    file = await stl(db_session, refs)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, lamp, file)
        response = post(client, online_pickup())
    assert response.status_code == 201, response.text
    snapshots = await line_snapshots(db_engine, response.json()["order"]["id"])
    assert snapshots == {"physical": "online", "stl": None}


async def test_dropping_an_owned_stl_lets_a_cash_only_product_be_paid_in_cash(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    cash, owned = (
        await physical(db_session, refs, accepted_payment_methods="cash"),
        await stl(db_session, refs),
    )
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, cash, owned)
        await seed_online_order(
            db_session, user_id=user_id, stl_id=owned, line_status="awaiting_delivery"
        )
        response = post(client, pickup_body(random_phone()), new_key())
    assert response.status_code == 201, response.text
    assert response.json()["order"]["payment_method"] == "cash"
    assert response.json()["dropped_lines"] == [
        {"product_id": str(owned), "reason": "already_owned"}
    ]


async def test_a_cash_only_cart_still_obeys_the_cash_switch(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Every existing cash rule still applies after the shared-method check (ADR-048 Q5)."""
    lamp = await physical(db_session, accepted_payment_methods="cash")
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        async with setting(db_engine, "cash_payment_enabled", False):
            response = await refused(client, db_engine, user_id, pickup_body(random_phone()))
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert response.json()["reason"] == "cash_disabled"


# --------------------------------------------------------------------- cart


@pytest.mark.parametrize(
    ("accepted", "with_stl", "expected"),
    [
        ([], False, ["online", "cash"]),
        (["online_or_cash", "cash"], False, ["cash"]),
        (["online_or_cash", "online"], True, ["online"]),
        (["cash", "online"], False, []),
        (["cash"], True, []),
    ],
)
async def test_the_cart_shows_the_methods_every_line_accepts(
    db_session: AsyncSession, accepted: list[str], with_stl: bool, expected: list[str]
) -> None:
    refs = await seed_refs(db_session)
    products = [await physical(db_session, refs, accepted_payment_methods=a) for a in accepted]
    if with_stl:
        products.append(await stl(db_session, refs))
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, *products)
        cart = client.get(CART)
    assert cart.status_code == 200, cart.text
    assert cart.json()["payment_methods"] == expected
