"""Seeding and probes for the VS-030 refund tests: paid orders written directly (online with
a `mock` payment, or cash with its handover payment), and the refund routes over HTTP."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure.verification import apply_provider_result
from tests.integration.deep_support import create_user, csrf
from tests.integration.fulfillment.delivery_support import line_of
from tests.integration.fulfillment.order_support import seed_physical_order

ADMIN = "/api/v1/admin"
REFUNDS = f"{ADMIN}/refunds"


@dataclass(frozen=True)
class Paid:
    order_id: uuid.UUID
    user_id: uuid.UUID
    physical: tuple[uuid.UUID, ...]
    stl: uuid.UUID | None
    phone: str


async def paid_online(
    db: AsyncSession,
    *,
    physical: tuple[str, ...] = ("delivered",),
    stl: str | None = "awaiting_delivery",
    fulfillment: str = "delivery",
) -> Paid:
    """Physical lines of 1000 each plus (optionally) one STL line of 500, paid in full."""
    order = await seed_physical_order(
        db,
        payment_method="online",
        payment_status="paid",
        line_states=physical,
        stl_line=stl,
        fulfillment=fulfillment,
    )
    stl_id = await line_of(db, order.order_id, "stl") if stl else None
    return Paid(order.order_id, order.user_id, order.line_ids, stl_id, order.phone)


async def paid_cash(
    db: AsyncSession, *, lines: tuple[str, ...] = ("delivered",), recorded_cents: int | None = None
) -> Paid:
    """A handed-over cash order; the cash payment records the live (uncancelled) lines."""
    order = await seed_physical_order(db, payment_method="cash", line_states=lines)
    live = sum(1000 for state in lines if state != "cancelled")
    admin = (await create_user(db, role=UserRole.ADMIN)).id
    at = datetime.now(UTC)
    await db.execute(
        text(
            "INSERT INTO payments (order_id, provider, order_payment_method, status,"
            " amount_cents, initiated_at, verified_at, recorded_by)"
            " VALUES (:o, 'cash', 'cash', 'paid', :a, :at, :at, :by)"
        ),
        {
            "o": order.order_id,
            "a": live if recorded_cents is None else recorded_cents,
            "at": at,
            "by": admin,
        },
    )
    await db.execute(
        text("UPDATE orders SET status = 'completed' WHERE id = :o"), {"o": order.order_id}
    )
    await db.commit()
    return Paid(order.order_id, order.user_id, order.line_ids, None, order.phone)


def key() -> str:
    return f"refund-{uuid.uuid4().hex}"


def create(
    client: TestClient,
    order_id: uuid.UUID,
    items: list[tuple[uuid.UUID, int]],
    *,
    idempotency_key: str | None = None,
    reason: str = "Goodwill for a scratch.",
) -> httpx.Response:
    response: httpx.Response = client.post(
        f"{ADMIN}/orders/{order_id}/refunds",
        json={
            "items": [{"order_item_id": str(i), "amount_cents": a} for i, a in items],
            "reason": reason,
        },
        headers=csrf(client) | {"Idempotency-Key": idempotency_key or key()},
    )
    return response


def act(
    client: TestClient, refund_id: str | uuid.UUID, action: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    headers = csrf(client)
    if action == "reissue":
        headers |= {"Idempotency-Key": key()}
    response: httpx.Response = client.post(
        f"{REFUNDS}/{refund_id}/{action}", json=body, headers=headers
    )
    return response


def ok(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


async def statuses(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[str, str]:
    """(order status, paid payment status)."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT o.status::text AS o, p.status::text AS p FROM orders o"
                    " JOIN payments p ON p.order_id = o.id"
                    " AND p.status IN ('paid', 'partially_refunded', 'refunded')"
                    " WHERE o.id = :o"
                ),
                {"o": order_id},
            )
        ).one()
    return row.o, row.p


async def line_state(engine: AsyncEngine, line_id: uuid.UUID) -> str:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT fulfillment_status::text FROM order_items WHERE id = :i"), {"i": line_id}
        )
    return str(found)


async def count(engine: AsyncEngine, sql: str, **params: Any) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(text(sql), params) or 0)


async def refund_count(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    return await count(engine, "SELECT count(*) FROM refunds WHERE order_id = :o", o=order_id)


def queue_ids(client: TestClient, order_id: uuid.UUID) -> set[str]:
    body = ok(client.get(REFUNDS, params={"order_id": str(order_id)}))
    return {item["id"] for item in body["items"]}


async def attempt(
    db: AsyncSession, order_id: uuid.UUID, *, status: str = "expired", amount: int = 1000
) -> uuid.UUID:
    """Another `mock` attempt of the order, not live (a retry's predecessor)."""
    at = datetime.now(UTC)
    payment_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO payments (order_id, provider, order_payment_method,"
                " provider_payment_id, status, amount_cents, initiated_at, failed_at, expired_at)"
                " VALUES (:o, 'mock', 'online', :ref, CAST(:s AS payment_status), :a, :at,"
                " :f, :x) RETURNING id"
            ),
            {
                "o": order_id,
                "ref": f"mock-{uuid.uuid4().hex}",
                "s": status,
                "a": amount,
                "at": at,
                "f": at if status == "failed" else None,
                "x": at if status == "expired" else None,
            },
        )
    ).scalar_one()
    await db.commit()
    return payment_id


async def late_capture(
    engine: AsyncEngine, payment_id: uuid.UUID, amount: int | None, currency: str | None = "USD"
) -> Outcome:
    """The provider's own answer for a non-live attempt, through VS-024's Tx B."""
    async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
        return await apply_provider_result(
            session,
            payment_id,
            ProviderResult("paid", amount, currency),
            source="reconcile",
            actor_user_id=None,
        )


async def late_refunds(engine: AsyncEngine, payment_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT id, status::text AS status, amount_cents, currency, reason, requested_by,"
                " reissue_of_refund_id, (SELECT count(*) FROM refund_items i"
                " WHERE i.refund_id = r.id) AS items"
                " FROM refunds r WHERE payment_id = :p AND kind = 'late_capture'"
                " ORDER BY created_at, id"
            ),
            {"p": payment_id},
        )
        return list(rows)


async def payment_of(engine: AsyncEngine, order_id: uuid.UUID) -> uuid.UUID:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT id FROM payments WHERE order_id = :o ORDER BY initiated_at, id LIMIT 1"),
            {"o": order_id},
        )
    assert isinstance(found, uuid.UUID)
    return found
