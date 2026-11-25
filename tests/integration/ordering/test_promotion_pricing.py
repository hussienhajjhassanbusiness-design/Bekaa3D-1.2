"""A promotion reprices the cart, checkout, the order's snapshot and the offer ceiling
through the one catalogue read (`SqlCartProductReader`): none of them computes a discount."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.domain.promotions import DiscountType, PromotionScope
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.promotion_support import (
    no_promotions,  # noqa: F401
    seed_promotion,
)
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.negotiation.offer_support import submit
from tests.integration.ordering.checkout_support import (
    buyer,
    checkout_body,
    post_checkout,
    shop_open,  # noqa: F401
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open", "no_promotions"),
]

CART = "/api/v1/cart"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


async def _stl(db: AsyncSession, cents: int = 2500) -> uuid.UUID:
    product = await seed_product(db, await seed_refs(db), type=ProductType.STL, price_cents=cents)
    return product.id


def _line(client: TestClient) -> dict[str, Any]:
    [line] = client.get(CART).json()["items"]
    return dict(line)


async def test_cart_and_checkout_charge_the_promotional_price(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    product = await _stl(db_session, 2500)
    await seed_promotion(db_session, discount_value=20)
    user = await buyer(client, db_session, product)

    line = _line(client)
    assert line["snapshot_price"]["amount_cents"] == 2000
    assert line["current_price"]["amount_cents"] == 2000
    assert line["price_changed"] is False

    response = post_checkout(client, checkout_body())
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    [ordered] = order["lines"]
    assert ordered["unit_price"]["amount_cents"] == 2000
    assert order["total"]["amount_cents"] == 2000

    # The order line keeps what was charged, whatever happens to the promotion after.
    async with db_engine.begin() as conn:
        await conn.execute(text("UPDATE promotions SET is_active = false"))
        stored = await conn.scalar(
            text("SELECT unit_price_cents FROM order_items WHERE user_id = :u"), {"u": user.id}
        )
    assert stored == 2000


async def test_a_promotion_starting_after_add_to_cart_is_a_price_change_to_confirm(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await _stl(db_session, 2500)
    await buyer(client, db_session, product)
    await seed_promotion(db_session, discount_type=DiscountType.FIXED, discount_value=500)

    line = _line(client)
    assert (line["snapshot_price"]["amount_cents"], line["current_price"]["amount_cents"]) == (
        2500,
        2000,
    )
    assert line["price_changed"] is True
    refused = post_checkout(client, checkout_body())
    assert_problem(refused, 409, "CART_PRICE_CHANGED")
    assert refused.json()["price_changes"][0]["new_amount_cents"] == 2000
    confirmed = post_checkout(
        client,
        checkout_body(
            accepted_price_changes=[
                {"product_id": str(product), "amount_cents": 2000, "currency": "USD"}
            ]
        ),
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["order"]["total"]["amount_cents"] == 2000


async def test_out_of_scope_products_keep_their_list_price_in_the_cart(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await _stl(db_session, 2500)
    await seed_promotion(db_session, scope=PromotionScope.PHYSICAL)
    await buyer(client, db_session, product)
    assert _line(client)["current_price"]["amount_cents"] == 2500


async def test_the_offer_ceiling_is_the_promotional_price(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await _stl(db_session, 2500)
    await seed_promotion(db_session, discount_value=20)
    user = await create_user(db_session)
    login(client, user.email)
    # Above today's effective price ($20) is refused, though below the $25 list price.
    assert_problem(submit(client, product, 2100), 422, "VALIDATION_ERROR")
    assert submit(client, product, 2000).status_code == 201
