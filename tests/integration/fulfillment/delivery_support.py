"""Seeding and probes for the VS-023b STL delivery tests."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pyotp
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from tests.integration.deep_support import (
    CONFIRM_PATH,
    PASSWORD,
    SETUP_PATH,
    async_client,
    create_user,
)
from tests.integration.payments.recovery_support import SeededOrder, seed_order

QUEUE = "/api/v1/admin/stl-deliveries"
EPOCH = datetime(2031, 1, 1, tzinfo=UTC)


def transition_path(order_id: uuid.UUID, item_id: uuid.UUID) -> str:
    return f"/api/v1/admin/orders/{order_id}/items/{item_id}/transition"


async def seed_stl_order(
    db: AsyncSession,
    *,
    line_status: str = "awaiting_delivery",
    queued_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
    delivered_by: uuid.UUID | None = None,
    physical: bool = False,
    order_status: str = "in_progress",
    email: str = "buyer@example.com",
) -> tuple[SeededOrder, uuid.UUID]:
    """A paid online order with one STL line in `line_status`; returns it and the line id."""
    order = await seed_order(
        db,
        placed_at=queued_at or datetime.now(UTC),
        user_id=user_id,
        physical=physical,
        customer_email_snapshot=email,
    )
    sets = "fulfillment_status = :s, created_at = :at"
    params: dict[str, Any] = {"s": line_status, "at": queued_at or datetime.now(UTC)}
    if line_status == "delivered":
        sets += ", fulfilled_at = :at, delivered_by = :by"
        params["by"] = delivered_by or (await create_user(db, role=UserRole.ADMIN)).id
    await db.execute(
        text(f"UPDATE order_items SET {sets} WHERE order_id = :o AND product_type = 'stl'"),
        params | {"o": order.order_id},
    )
    await db.execute(
        text("UPDATE orders SET status = :s WHERE id = :o"),
        {"s": order_status, "o": order.order_id},
    )
    await db.commit()
    return order, await line_of(db, order.order_id)


async def line_of(db: AsyncSession, order_id: uuid.UUID, product_type: str = "stl") -> uuid.UUID:
    found = await db.scalar(
        text("SELECT id FROM order_items WHERE order_id = :o AND product_type = :t"),
        {"o": order_id, "t": product_type},
    )
    assert found is not None
    return uuid.UUID(str(found))


EFFECTS = """
SELECT
 (SELECT count(*) FROM order_status_history WHERE order_item_id = :i) AS history,
 (SELECT count(*) FROM audit_logs WHERE action = 'stl.delivered' AND entity_id = :i) AS audits,
 (SELECT count(*) FROM notifications WHERE payload->>'event' = 'stl.delivered'
    AND payload->>'item_id' = CAST(:i AS text)) AS notices,
 (SELECT count(*) FROM email_outbox WHERE template = 'order_stl_delivered'
    AND payload->>'item_id' = CAST(:i AS text)) AS emails
"""


async def effects(engine: AsyncEngine, item_id: uuid.UUID) -> tuple[int, int, int, int]:
    """(history rows, audit rows, notifications, outbox emails) written for one line."""
    async with engine.connect() as conn:
        row = (await conn.execute(text(EFFECTS), {"i": item_id})).one()
    return row.history, row.audits, row.notices, row.emails


async def line_row(engine: AsyncEngine, item_id: uuid.UUID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT i.fulfillment_status, i.fulfilled_at, i.delivered_by,"
                    " o.status AS order_status"
                    " FROM order_items i JOIN orders o ON o.id = i.order_id WHERE i.id = :i"
                ),
                {"i": item_id},
            )
        ).one()


async def admin_client(app: FastAPI, db: AsyncSession) -> tuple[httpx.AsyncClient, uuid.UUID]:
    """An MFA-complete administrator on its own client and IP (for racing two of them)."""
    user = await create_user(db, role=UserRole.ADMIN)
    client = async_client(app)
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    setup = await client.post(SETUP_PATH, json={"current_password": PASSWORD}, headers=headers)
    assert setup.status_code == 200, setup.text
    code = pyotp.TOTP(setup.json()["secret"]).now()
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    confirm = await client.post(CONFIRM_PATH, json={"code": code}, headers=headers)
    assert confirm.status_code == 200, confirm.text
    return client, user.id


async def mark_sent(
    client: httpx.AsyncClient, order_id: uuid.UUID, item_id: uuid.UUID
) -> httpx.Response:
    return await client.post(
        transition_path(order_id, item_id),
        json={"target_status": "delivered"},
        headers={"X-CSRF-Token": client.cookies["csrf_token"]},
    )


async def wait_for_lock_waiters(engine: AsyncEngine, count: int, seconds: float = 10.0) -> None:
    """Block until `count` backends wait on the `orders` row lock, or fail the test."""
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database() AND query ILIKE '%FROM orders%FOR UPDATE%'"
                )
            )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"fewer than {count} requests ever waited on the orders lock")
