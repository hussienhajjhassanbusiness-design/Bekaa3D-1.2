"""Helpers for the physical and cash checkout suites (VS-028 plan 6.2): products, addresses,
settings that are restored, a one-call cash checkout, and seeded cash orders and blocks."""

import json
import random
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.core.security import hash_phone
from app.identity.infrastructure.models import AddressModel
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import create_user, csrf, login
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    add_to_cart,
    checkout_body,
    new_key,
)


def random_phone() -> str:
    """A fresh valid E.164 mobile number, so cash limits never leak between tests."""
    return f"+96171{random.SystemRandom().randrange(100000, 999999)}"


def usd(cents: int) -> dict[str, Any]:
    """A `PriceRead` body."""
    return {"amount_cents": cents, "currency": "USD"}


def spaced(e164: str) -> str:
    """The same number as a customer might type it."""
    return f"{e164[:4]} {e164[4:6]} {e164[6:9]} {e164[9:]}"


async def physical(db: AsyncSession, refs: Refs | None = None, **over: Any) -> uuid.UUID:
    product = await seed_product(db, refs or await seed_refs(db), **over)
    return product.id


async def stl(db: AsyncSession, refs: Refs | None = None, **over: Any) -> uuid.UUID:
    values = {"price_cents": 900} | over
    product = await seed_product(db, refs or await seed_refs(db), type=ProductType.STL, **values)
    return product.id


async def seed_address(
    db: AsyncSession, user_id: uuid.UUID, phone: str | None = None, **over: Any
) -> uuid.UUID:
    values: dict[str, Any] = {
        "user_id": user_id,
        "label": "Home",
        "recipient_name": "Rita Customer",
        "phone": phone or random_phone(),
        "governorate": "beirut",
        "city": "Beirut",
        "street": "Hamra St",
        "landmark_notes": "Blue door",
    }
    row = AddressModel(**(values | over))
    db.add(row)
    await db.commit()
    return row.id


@asynccontextmanager
async def setting(engine: AsyncEngine, key: str, value: Any) -> AsyncIterator[None]:
    """Set a registered setting for the block, then put the old value back."""
    sql = text("UPDATE settings SET value = CAST(:v AS jsonb) WHERE key = :k")
    async with engine.begin() as conn:
        before = await conn.scalar(
            text("SELECT value::text FROM settings WHERE key = :k"), {"k": key}
        )
        await conn.execute(sql, {"k": key, "v": json.dumps(value)})
    try:
        yield
    finally:
        async with engine.begin() as conn:
            await conn.execute(sql, {"k": key, "v": before})


def cash_body(**over: Any) -> dict[str, Any]:
    return checkout_body(payment_method="cash", accept_cash_terms=True) | over


def delivery_body(address_id: uuid.UUID, **over: Any) -> dict[str, Any]:
    return cash_body(fulfillment_method="delivery", address_id=str(address_id)) | over


def pickup_body(phone: str, **over: Any) -> dict[str, Any]:
    return cash_body(fulfillment_method="pickup", contact_phone=phone) | over


def post(
    client: TestClient, body: dict[str, Any], key: str | None = None, **headers: str
) -> httpx.Response:
    sent = csrf(client) | {"Idempotency-Key": key or new_key()} | headers
    response: httpx.Response = client.post(CHECKOUT, json=body, headers=sent)
    return response


async def signed_in_buyer(client: TestClient, db: AsyncSession, *products: uuid.UUID) -> uuid.UUID:
    user = await create_user(db)
    login(client, user.email)
    for product_id in products:
        add_to_cart(client, product_id)
    return user.id


async def seed_cash_order(
    db: AsyncSession,
    user_id: uuid.UUID,
    phone: str,
    *,
    status: str = "in_progress",
    line_status: str = "pending",
    total_cents: int = 1000,
) -> uuid.UUID:
    """A cash order with one physical line, written directly (VS-029 and VS-031 own the
    paths that move it). The phone is stored E.164 with its keyed hash."""
    order_id, product_id = uuid.uuid4(), await physical(db, price_cents=total_cents)
    now = datetime.now(UTC)
    await db.execute(
        text(
            "INSERT INTO orders (id, order_number, user_id, customer_email_snapshot, source,"
            " status, fulfillment_method, payment_method, subtotal_cents, tax_cents,"
            " total_cents, currency, contact_phone_snapshot, contact_phone_hash,"
            " terms_accepted_at, cash_terms_accepted_at, placed_at)"
            " SELECT :id, :n, u.id, u.email, 'cart', CAST(:st AS order_status), 'pickup', 'cash',"
            " :t, 0, :t, 'USD', :ph, :h, :now, :now, :now FROM users u WHERE u.id = :u"
        ),
        {
            "id": order_id,
            "n": f"B3D-{uuid.uuid4().hex[:8].upper()}",
            "u": user_id,
            "st": status,
            "t": total_cents,
            "ph": phone,
            "h": hash_phone(phone),
            "now": now,
        },
    )
    await db.execute(
        text(
            "INSERT INTO order_items (order_id, user_id, product_id, product_type,"
            " product_name_snapshot, unit_price_cents, quantity, line_total_cents, currency,"
            " fulfillment_status, payment_method, lead_time_days_snapshot, batch_size_snapshot)"
            " VALUES (:o, :u, :p, 'physical', 'Lamp', :t, 1, :t, 'USD',"
            " CAST(:ls AS order_item_status), 'cash', 3, 2)"
        ),
        {"o": order_id, "u": user_id, "p": product_id, "t": total_cents, "ls": line_status},
    )
    await db.commit()
    return order_id


async def seed_block(
    db: AsyncSession, user_id: uuid.UUID, phone: str, *, order_id: uuid.UUID | None = None
) -> None:
    """An uncleared block on `user_id` and the phone's hash, on a cancelled cash order."""
    order = order_id or await seed_cash_order(
        db, user_id, phone, status="cancelled", line_status="cancelled"
    )
    await db.execute(
        text(
            "INSERT INTO cash_payment_blocks (user_id, contact_phone_hash, order_id, reason)"
            " VALUES (:u, :h, :o, 'refused')"
        ),
        {"u": user_id, "h": hash_phone(phone), "o": order},
    )
    await db.commit()
