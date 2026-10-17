"""Helpers for the checkout suites: a signed-in buyer with a cart, the request, and row
counts that show what a refused checkout left behind (VS-023 plan 6.2)."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.infrastructure.models import UserModel
from tests.integration.deep_support import create_user, csrf, login

CHECKOUT = "/api/v1/checkout"
ITEMS = "/api/v1/cart/items"


@pytest_asyncio.fixture
async def shop_open(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """`accepting_orders` defaults to false (settings-registry.md); restored afterwards."""
    sql = "UPDATE settings SET value = CAST(:v AS jsonb) WHERE key = 'accepting_orders'"
    async with db_engine.begin() as conn:
        before = await conn.scalar(
            text("SELECT value::text FROM settings WHERE key = 'accepting_orders'")
        )
        await conn.execute(text(sql), {"v": "true"})
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text(sql), {"v": before})


def checkout_body(**over: Any) -> dict[str, Any]:
    return {
        "payment_method": "online",
        "accept_terms": True,
        "accept_digital_final_sale": True,
    } | over


def new_key() -> str:
    return f"key-{uuid.uuid4().hex}"


def post_checkout(
    client: TestClient, body: dict[str, Any] | None = None, key: str | None = None
) -> httpx.Response:
    headers = csrf(client) | {"Idempotency-Key": key or new_key()}
    response: httpx.Response = client.post(
        CHECKOUT, json=checkout_body() if body is None else body, headers=headers
    )
    return response


def add_to_cart(client: TestClient, product_id: uuid.UUID, quantity: int = 1) -> None:
    response = client.post(
        ITEMS, json={"product_id": str(product_id), "quantity": quantity}, headers=csrf(client)
    )
    assert response.status_code == 200, response.text


async def buyer(client: TestClient, db: AsyncSession, *products: uuid.UUID) -> UserModel:
    """A verified customer, signed in, with one of each product in the cart."""
    user = await create_user(db)
    login(client, user.email)
    for product_id in products:
        add_to_cart(client, product_id)
    return user


@dataclass(frozen=True)
class Rows:
    orders: int
    lines: int
    payments: int
    claims: int
    cart_lines: int
    history: int


async def rows(engine: AsyncEngine, user_id: uuid.UUID) -> Rows:
    """Every table checkout writes, counted for one customer."""
    sql = """
        SELECT
          (SELECT count(*) FROM orders WHERE user_id = :u) AS orders,
          (SELECT count(*) FROM order_items WHERE user_id = :u) AS lines,
          (SELECT count(*) FROM payments p JOIN orders o ON o.id = p.order_id
            WHERE o.user_id = :u) AS payments,
          (SELECT count(*) FROM idempotency_records WHERE user_id = :u) AS claims,
          (SELECT count(*) FROM cart_items ci JOIN carts c ON c.id = ci.cart_id
            WHERE c.user_id = :u) AS cart_lines,
          (SELECT count(*) FROM order_status_history h JOIN orders o ON o.id = h.order_id
            WHERE o.user_id = :u) AS history
    """
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), {"u": user_id})).one()
    return Rows(**row._mapping)


async def set_price(db: AsyncSession, product_id: uuid.UUID, cents: int) -> None:
    await db.execute(
        text("UPDATE products SET price_cents = :c WHERE id = :i"), {"c": cents, "i": product_id}
    )
    await db.commit()
