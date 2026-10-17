"""Seeding helpers for orders and payments written straight to the database."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


async def seed_online_order(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    stl_id: uuid.UUID,
    line_status: str = "pending",
    total_cents: int = 1000,
    **over: Any,
) -> uuid.UUID:
    """One digital order with one STL line, committed; returns the order id."""
    oid = uuid.uuid4()
    order = {
        "id": oid,
        "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
        "user_id": user_id,
        "customer_email_snapshot": "buyer@example.com",
        "source": "cart",
        "status": "pending_payment" if line_status == "pending" else "in_progress",
        "payment_method": "online",
        "subtotal_cents": total_cents,
        "total_cents": total_cents,
        "terms_accepted_at": NOW,
        "digital_terms_accepted_at": NOW,
        "digital_terms_version": "2026-10-17",
        "placed_at": NOW,
    } | over
    line = {
        "order_id": oid,
        "user_id": user_id,
        "payment_method": "online",
        "product_id": stl_id,
        "product_type": "stl",
        "product_name_snapshot": "Seeded STL",
        "unit_price_cents": total_cents,
        "quantity": 1,
        "line_total_cents": total_cents,
        "fulfillment_status": line_status,
    }
    if line_status == "delivered":
        line |= {"fulfilled_at": NOW, "delivered_by": user_id}
    for table, row in (("orders", order), ("order_items", line)):
        await db.execute(
            text(
                f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"
            ),
            row,
        )
    await db.commit()
    return oid
