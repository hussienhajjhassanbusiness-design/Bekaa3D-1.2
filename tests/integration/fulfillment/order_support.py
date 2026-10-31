"""Seeding and probes for the VS-029 admin order tests: physical orders in any line state,
written directly (later slices own some of the paths that reach those states)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.core.security import hash_phone
from app.identity.domain.enums import UserRole
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user, csrf
from tests.integration.ordering.physical_support import random_phone

ORDERS = "/api/v1/admin/orders"
REACHED_PAID = ("paid", "partially_refunded", "refunded")


@dataclass(frozen=True)
class PhysicalOrder:
    order_id: uuid.UUID
    user_id: uuid.UUID
    order_number: str
    line_ids: tuple[uuid.UUID, ...]
    phone: str


def order_path(order_id: uuid.UUID) -> str:
    return f"{ORDERS}/{order_id}"


def transition_path(order_id: uuid.UUID, item_id: uuid.UUID) -> str:
    return f"{ORDERS}/{order_id}/items/{item_id}/transition"


def handover_path(order_id: uuid.UUID) -> str:
    return f"{ORDERS}/{order_id}/cash-handover"


def move(
    client: TestClient, order: PhysicalOrder, target: str, line: int = 0, **body: Any
) -> httpx.Response:
    response: httpx.Response = client.post(
        transition_path(order.order_id, order.line_ids[line]),
        json={"target_status": target} | body,
        headers=csrf(client),
    )
    return response


def hand_over(client: TestClient, order: PhysicalOrder, amount_cents: int) -> httpx.Response:
    response: httpx.Response = client.post(
        handover_path(order.order_id),
        json={"amount_cents": amount_cents, "currency": "USD"},
        headers=csrf(client),
    )
    return response


def _default_status(payment_method: str, payment_status: str | None) -> str:
    if payment_method == "online" and payment_status not in REACHED_PAID:
        return "pending_payment"
    return "in_progress"


async def seed_physical_order(
    db: AsyncSession,
    *,
    payment_method: str = "cash",
    fulfillment: str = "delivery",
    line_states: Sequence[str] = ("pending",),
    line_totals: Sequence[int] | None = None,
    payment_status: str | None = None,
    order_status: str | None = None,
    user_id: uuid.UUID | None = None,
    placed_at: datetime | None = None,
    email: str = "buyer@example.com",
    stl_line: str | None = None,
    before_vs049: bool = False,
) -> PhysicalOrder:
    """A physical order; online ones get one `mock` payment in `payment_status` (none if
    None). `stl_line` adds an STL line in that state (online only). `before_vs049`: for a
    schema migrated below 089f97a72014."""
    user_id = user_id or (await create_user(db)).id
    totals = list(line_totals or [1000] * len(line_states))
    refs = await seed_refs(db)
    order_id, number, phone = uuid.uuid4(), f"B3D-{uuid.uuid4().hex[:8].upper()}", random_phone()
    at = placed_at or datetime.now(UTC)
    status = order_status or _default_status(payment_method, payment_status)
    stl_total = 500 if stl_line else 0
    total = sum(totals) + stl_total
    address = (
        {"rn": "Rana", "gov": "Beqaa", "city": "Zahle", "lm": "Blue door"}
        if fulfillment == "delivery"
        else {"rn": None, "gov": None, "city": None, "lm": None}
    )
    await db.execute(
        text(
            "INSERT INTO orders (id, order_number, user_id, customer_email_snapshot, source,"
            " status, fulfillment_method, payment_method, subtotal_cents, tax_cents,"
            " total_cents, recipient_name, governorate, city, landmark_notes,"
            " contact_phone_snapshot, contact_phone_hash, terms_accepted_at,"
            " digital_terms_accepted_at, digital_terms_version, cash_terms_accepted_at,"
            " placed_at, cancelled_at)"
            " VALUES (:id, :n, :u, :e, 'cart', CAST(:st AS order_status),"
            " CAST(:fm AS fulfillment_method), CAST(:pm AS payment_method), :t, 0, :t,"
            " :rn, :gov, :city, :lm, :ph, :h, :at, :dt, :dv, :ct, :at, :x)"
        ),
        {
            "id": order_id,
            "n": number,
            "u": user_id,
            "e": email,
            "st": status,
            "fm": fulfillment,
            "pm": payment_method,
            "t": total,
            "ph": phone,
            "h": hash_phone(phone),
            "at": at,
            "dt": at if stl_line else None,
            "dv": "2026-10-17" if stl_line else None,
            "ct": at if payment_method == "cash" else None,
            "x": at if status == "cancelled" else None,
        }
        | address,
    )
    ids = []
    for state, line_total in zip(line_states, totals, strict=True):
        product = await (_product_before_vs049(db, refs) if before_vs049 else _product(db, refs))
        line_id = uuid.uuid4()
        snapshot = (
            ("", "")
            if before_vs049
            else (", accepted_payment_methods_snapshot", ", 'online_or_cash'")
        )
        await db.execute(
            text(
                "INSERT INTO order_items (id, order_id, user_id, product_id, product_type,"
                " product_name_snapshot, unit_price_cents, quantity, line_total_cents,"
                " fulfillment_status, payment_method, lead_time_days_snapshot,"
                f" batch_size_snapshot, cancelled_at{snapshot[0]})"
                " VALUES (:id, :o, :u, :p, 'physical', 'Lamp', :t, 1, :t,"
                " CAST(:s AS order_item_status), CAST(:pm AS payment_method), 3, 2,"
                f" :c{snapshot[1]})"
            ),
            {
                "id": line_id,
                "o": order_id,
                "u": user_id,
                "p": product,
                "t": line_total,
                "s": state,
                "pm": payment_method,
                "c": at if state == "cancelled" else None,
            },
        )
        ids.append(line_id)
    if stl_line:
        await _seed_stl_line(db, refs, order_id, user_id, stl_line, stl_total)
    if payment_status is not None:
        await seed_payment(db, order_id, total, payment_status, at=at)
    await db.commit()
    return PhysicalOrder(order_id, user_id, number, tuple(ids), phone)


async def _product(db: AsyncSession, refs: Any) -> uuid.UUID:
    return (await seed_product(db, refs)).id


async def _product_before_vs049(db: AsyncSession, refs: Any) -> uuid.UUID:
    """The ORM writes every mapped column; a schema below 089f97a72014 lacks one of them."""
    product_id: uuid.UUID = await db.scalar(
        text(
            "INSERT INTO products (type, category_id, name, slug, price_cents, is_visible,"
            " purchase_mode, production_lead_time_days, batch_size, max_quantity_per_line)"
            " VALUES ('physical', :c, 'Lamp', :s, 1000, true, 'online_only', 3, 2, 5)"
            " RETURNING id"
        ),
        {"c": refs.category.id, "s": f"p-{uuid.uuid4().hex[:12]}"},
    )
    return product_id


async def _seed_stl_line(
    db: AsyncSession, refs: Any, order_id: uuid.UUID, user_id: uuid.UUID, state: str, total: int
) -> None:
    product = (await seed_product(db, refs, type=ProductType.STL)).id
    await db.execute(
        text(
            "INSERT INTO order_items (order_id, user_id, product_id, product_type,"
            " product_name_snapshot, unit_price_cents, quantity, line_total_cents,"
            " fulfillment_status, payment_method, fulfilled_at, delivered_by)"
            " VALUES (:o, :u, :p, 'stl', 'Model', :t, 1, :t, CAST(:s AS order_item_status),"
            " 'online', :f, :by)"
        ),
        {
            "o": order_id,
            "u": user_id,
            "p": product,
            "t": total,
            "s": state,
            "f": datetime.now(UTC) if state == "delivered" else None,
            "by": (await create_user(db, role=UserRole.ADMIN)).id if state == "delivered" else None,
        },
    )


async def seed_payment(
    db: AsyncSession, order_id: uuid.UUID, amount: int, status: str, *, at: datetime
) -> None:
    paid = status in REACHED_PAID
    await db.execute(
        text(
            "INSERT INTO payments (order_id, provider, order_payment_method, provider_payment_id,"
            " status, amount_cents, initiated_at, verified_at, failed_at, expired_at)"
            " VALUES (:o, 'mock', 'online', :ref, CAST(:s AS payment_status), :a, :at,"
            " :v, :f, :x)"
        ),
        {
            "o": order_id,
            "ref": f"mock-{uuid.uuid4().hex}",
            "s": status,
            "a": amount,
            "at": at,
            "v": at if paid else None,
            "f": at if status == "failed" else None,
            "x": at if status == "expired" else None,
        },
    )


EFFECTS = """
SELECT
 (SELECT count(*) FROM order_status_history WHERE order_id = :o) AS history,
 (SELECT count(*) FROM audit_logs WHERE entity_id = :o
    OR entity_id IN (SELECT id FROM order_items WHERE order_id = :o)) AS audits,
 (SELECT count(*) FROM notifications WHERE payload->>'order_id' = CAST(:o AS text)) AS notices,
 (SELECT count(*) FROM email_outbox WHERE payload->>'order_id' = CAST(:o AS text)) AS emails,
 (SELECT count(*) FROM payments WHERE order_id = :o AND provider = 'cash') AS cash
"""


async def effects(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[int, int, int, int, int]:
    """(history rows, audit rows, notifications, emails, cash payments) for one order."""
    async with engine.connect() as conn:
        row = (await conn.execute(text(EFFECTS), {"o": order_id})).one()
    return row.history, row.audits, row.notices, row.emails, row.cash


async def states(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[str, list[str]]:
    """(order status, line states in id order)."""
    async with engine.connect() as conn:
        status = await conn.scalar(text("SELECT status FROM orders WHERE id = :o"), {"o": order_id})
        lines = await conn.scalars(
            text(
                "SELECT fulfillment_status FROM order_items WHERE order_id = :o"
                " AND product_type = 'physical' ORDER BY id"
            ),
            {"o": order_id},
        )
        return str(status), [str(s) for s in lines]


async def emails(engine: AsyncEngine, order_id: uuid.UUID) -> list[tuple[str, dict[str, Any]]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT template, payload FROM email_outbox"
                " WHERE payload->>'order_id' = CAST(:o AS text) ORDER BY created_at, id"
            ),
            {"o": str(order_id)},
        )
        return [(row.template, row.payload) for row in rows]


async def notifications(engine: AsyncEngine, order_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text(
                "SELECT payload->>'event' FROM notifications"
                " WHERE payload->>'order_id' = CAST(:o AS text) ORDER BY created_at, id"
            ),
            {"o": str(order_id)},
        )
        return [str(event) for event in rows]
