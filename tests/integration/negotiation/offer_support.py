"""Helpers for the offer suites (VS-039): products, offers seeded in any state, the shop's
kill switch and row counts showing what a refused submission left behind."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import csrf

OFFERS = "/api/v1/offers"
MY_OFFERS = "/api/v1/me/offers"
ADMIN_OFFERS = "/api/v1/admin/offers"
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


async def _set(engine: AsyncEngine, key: str, value: str) -> str:
    async with engine.begin() as conn:
        before = await conn.scalar(
            text("SELECT value::text FROM settings WHERE key = :k"), {"k": key}
        )
        await conn.execute(
            text("UPDATE settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            {"k": key, "v": value},
        )
    return str(before)


@pytest_asyncio.fixture
async def shop_open(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """`accepting_orders` defaults to false (settings-registry.md); restored afterwards."""
    before = await _set(db_engine, "accepting_orders", "true")
    yield
    await _set(db_engine, "accepting_orders", before)


async def set_setting(engine: AsyncEngine, key: str, value: str) -> str:
    """Returns the previous JSON text so a test can restore it."""
    return await _set(engine, key, value)


async def stl(db: AsyncSession, **over: Any) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db), type=ProductType.STL, **over)).id


async def physical(db: AsyncSession) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db))).id


def submit(
    client: TestClient, product_id: uuid.UUID, amount: int = 800, **over: Any
) -> httpx.Response:
    body = {"product_id": str(product_id), "amount_cents": amount, "currency": "USD"} | over
    response: httpx.Response = client.post(OFFERS, json=body, headers=csrf(client))
    return response


async def seed_offer(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    status: str = "awaiting_admin",
    responds_by: datetime | None = None,
    created_at: datetime | None = None,
    **over: Any,
) -> uuid.UUID:
    """One offer in any state, with a `submitted` round, committed directly."""
    at = created_at or datetime.now(UTC)
    turn = {"awaiting_admin": "admin", "awaiting_customer": "customer"}.get(status)
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "product_id": product_id,
        "status": status,
        "turn": turn,
        "initial_amount_cents": 800,
        "current_amount_cents": 800,
        "responds_by": responds_by if responds_by else at + timedelta(hours=48),
        "created_at": at,
        "updated_at": at,
    }
    if status in {"accepted", "paid", "checkout_expired"}:
        row |= {
            "agreed_amount_cents": 800,
            "accepted_at": at,
            "checkout_expires_at": at + timedelta(hours=24),
        }
    if status == "rejected":
        row |= {"rejected_at": at, "cooldown_until": at + timedelta(days=7)}
    row |= over
    columns = ", ".join(row)
    values = ", ".join(f":{c}" for c in row)
    await db.execute(text(f"INSERT INTO offers ({columns}) VALUES ({values})"), row)
    await db.execute(
        text(
            "INSERT INTO offer_rounds (offer_id, sequence, actor, action, amount_cents, currency)"
            " VALUES (:o, 1, 'customer', 'submitted', 800, 'USD')"
        ),
        {"o": row["id"]},
    )
    await db.commit()
    return uuid.UUID(str(row["id"]))


@dataclass(frozen=True)
class OfferRows:
    offers: int
    rounds: int
    audits: int
    notifications: int


async def offer_rows(engine: AsyncEngine, user_id: uuid.UUID) -> OfferRows:
    """What a submission writes: offers, rounds, audit rows and admin notifications."""
    sql = """
        SELECT
          (SELECT count(*) FROM offers WHERE user_id = :u) AS offers,
          (SELECT count(*) FROM offer_rounds r JOIN offers o ON o.id = r.offer_id
            WHERE o.user_id = :u) AS rounds,
          (SELECT count(*) FROM audit_logs WHERE actor_user_id = :u
            AND action = 'offer.submitted') AS audits,
          (SELECT count(*) FROM notifications WHERE type = 'offer'
            AND payload->>'offer_id' IN (SELECT id::text FROM offers WHERE user_id = :u))
            AS notifications
    """
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), {"u": user_id})).one()
    return OfferRows(**row._mapping)
