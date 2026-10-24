"""Helpers for the VS-031 cancellation tests: the two cancel routes over HTTP, and probes
for the refund, the block and the customer's own-cancel stamp they leave behind."""

import uuid
from collections.abc import Callable
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import app as main_app
from tests.integration.deep_support import client_for, csrf, login
from tests.integration.fulfillment.order_support import ORDERS


def customer_cancel_path(order_id: uuid.UUID) -> str:
    return f"/api/v1/me/orders/{order_id}/cancel"


def customer_cancel(
    client: TestClient, order_id: uuid.UUID, reason: str | None = None
) -> httpx.Response:
    body = {} if reason is None else {"reason": reason}
    response: httpx.Response = client.post(
        customer_cancel_path(order_id), json=body, headers=csrf(client)
    )
    return response


def admin_cancel(
    client: TestClient,
    order_id: uuid.UUID,
    cancel_reason: str | None = None,
    reason: str = "Printer failure",
) -> httpx.Response:
    body: dict[str, Any] = {"reason": reason}
    if cancel_reason is not None:
        body["cancel_reason"] = cancel_reason
    response: httpx.Response = client.post(
        f"{ORDERS}/{order_id}/cancel", json=body, headers=csrf(client)
    )
    return response


def as_customer[T](email: str, call: Callable[[TestClient], T]) -> T:
    """One client at a time: a customer and an administrator never share an event loop."""
    with client_for(main_app) as client:
        login(client, email)
        return call(client)


async def refunds_of(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT r.id, r.kind::text AS kind, r.status::text AS status, r.amount_cents,"
                " r.requested_by, r.approved_by,"
                " (SELECT json_object_agg(i.order_item_id, i.amount_cents) FROM refund_items i"
                "  WHERE i.refund_id = r.id) AS items"
                " FROM refunds r WHERE r.order_id = :o ORDER BY r.created_at, r.id"
            ),
            {"o": order_id},
        )
        return list(rows)


async def blocks_of(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT user_id, contact_phone_hash, reason::text AS reason"
                " FROM cash_payment_blocks WHERE order_id = :o"
            ),
            {"o": order_id},
        )
        return list(rows)


async def reasons_of(engine: AsyncEngine, order_id: uuid.UUID) -> list[str | None]:
    """`cancel_reason` per physical line, in id order."""
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text(
                "SELECT cancel_reason::text FROM order_items WHERE order_id = :o"
                " AND product_type = 'physical' ORDER BY id"
            ),
            {"o": order_id},
        )
        return list(rows)


async def customer_cancelled_at(engine: AsyncEngine, order_id: uuid.UUID) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(
            text("SELECT customer_cancelled_at FROM orders WHERE id = :o"), {"o": order_id}
        )


async def cancel_audits(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT actor_user_id, after_data FROM audit_logs"
                " WHERE action = 'order.cancelled' AND entity_id = :o ORDER BY created_at"
            ),
            {"o": order_id},
        )
        return list(rows)
