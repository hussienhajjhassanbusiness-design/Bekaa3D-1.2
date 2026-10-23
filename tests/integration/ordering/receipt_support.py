"""Paths and probes for the VS-029b receipt-confirmation and problem-report tests."""

import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

CONFIRM = "confirm-receipt"
REPORT = "report-problem"
ACTIONS = (CONFIRM, REPORT)
DONE = {"delivery": "delivered", "pickup": "picked_up"}
EVENT = "order.problem_reported"


def action_path(order_id: uuid.UUID, action: str) -> str:
    return f"/api/v1/me/orders/{order_id}/{action}"


def body_for(action: str, message: str = "The lamp arrived cracked.") -> dict[str, Any] | None:
    return {"message": message} if action == REPORT else None


async def act(
    client: httpx.AsyncClient, order_id: uuid.UUID, action: str, **body: Any
) -> httpx.Response:
    headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
    payload = body or body_for(action)
    return await client.post(action_path(order_id, action), json=payload, headers=headers)


async def stamps(engine: AsyncEngine, order_id: uuid.UUID) -> list[tuple[Any, Any]]:
    """(receipt_confirmed_at, problem_reported_at) per line, in id order."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT receipt_confirmed_at, problem_reported_at FROM order_items"
                " WHERE order_id = :o ORDER BY id"
            ),
            {"o": order_id},
        )
        return [(row[0], row[1]) for row in rows]


async def linked_messages(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT id, user_id, order_id, name, email, phone, subject, message, status"
                " FROM contact_messages WHERE order_id = :o ORDER BY created_at, id"
            ),
            {"o": order_id},
        )
        return list(rows.all())


async def problem_notices(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    """(user_id, type, payload) of every `order.problem_reported` notification."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT user_id, type, payload FROM notifications"
                " WHERE payload->>'event' = :e AND payload->>'order_id' = CAST(:o AS text)"
            ),
            {"e": EVENT, "o": str(order_id)},
        )
        return list(rows.all())


async def receipt_audits(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT action, actor_user_id, after_data FROM audit_logs WHERE entity_id = :o"
                " AND action IN ('order.receipt_confirmed', 'order.problem_reported')"
                " ORDER BY created_at, id"
            ),
            {"o": order_id},
        )
        return list(rows.all())


async def active_admin_ids(engine: AsyncEngine) -> set[uuid.UUID]:
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text(
                "SELECT id FROM users WHERE role = 'admin' AND is_active"
                " AND deleted_at IS NULL AND anonymized_at IS NULL"
            )
        )
        return set(rows)
