"""A seeded order with a pending mock payment, and the counts that show how many times
it was paid (VS-023 plan 6.2, 6.3): exactly one paid transition is the invariant."""

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.core.config import get_settings
from app.payments.application.ports import CreatePayment
from app.payments.infrastructure.providers.mock import MockPaymentProvider, sign
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.payments.support import NOW, seed_online_order

WEBHOOK = "/api/v1/webhooks/payments/mock"


@pytest_asyncio.fixture(name="mock")
async def mock_fixture() -> AsyncIterator[MockPaymentProvider]:
    """A separate instance on the app's Redis: what a test or `mock_pay.py` drives."""
    provider = MockPaymentProvider(
        redis_url=get_settings().redis_url,
        webhook_secret=get_settings().mock_webhook_secret,
        frontend_base_url="",
    )
    yield provider
    await provider.aclose()


@dataclass(frozen=True)
class Seeded:
    user_id: uuid.UUID
    order_id: uuid.UUID
    payment_id: uuid.UUID
    reference: str
    email: str


async def pending_payment(
    db: AsyncSession,
    mock: MockPaymentProvider,
    *,
    total_cents: int = 1000,
    store_reference: bool = True,
) -> Seeded:
    """An unpaid STL order and its pending attempt, known to the mock. Without
    `store_reference` the row looks like the checkout Tx2 crash: no provider id."""
    user = await create_user(db)
    stl = (await seed_product(db, await seed_refs(db), type=ProductType.STL)).id
    order_id = await seed_online_order(db, user_id=user.id, stl_id=stl, total_cents=total_cents)
    payment_id = uuid.uuid4()
    created = await mock.create_payment(
        CreatePayment(payment_id, "B3D-SEEDED00", total_cents, "USD", "")
    )
    await db.execute(
        text(
            "INSERT INTO payments (id, order_id, provider, order_payment_method, status,"
            " amount_cents, initiated_at, provider_payment_id)"
            " VALUES (:id, :o, 'mock', 'online', 'pending', :a, :t, :r)"
        ),
        {
            "id": payment_id,
            "o": order_id,
            "a": total_cents,
            "t": NOW,
            "r": created.provider_payment_id if store_reference else None,
        },
    )
    await db.commit()
    assert created.provider_payment_id is not None  # the mock always names one
    return Seeded(user.id, order_id, payment_id, created.provider_payment_id, user.email)


def event_body(
    seeded: Seeded, *, event_id: str | None = None, reference: bool = True, ours: bool = True
) -> bytes:
    """A mock event naming the payment by our id, its provider id, or both."""
    payload: dict[str, Any] = {"event_id": event_id or f"ev_{uuid.uuid4().hex}", "type": "payment"}
    if ours:
        payload["payment_reference"] = str(seeded.payment_id)
    if reference:
        payload["provider_payment_id"] = seeded.reference
    return json.dumps(payload).encode()


def signed(body: bytes, secret: str | None = None) -> dict[str, str]:
    return {
        "X-Mock-Signature": sign(secret or get_settings().mock_webhook_secret, body),
        "Content-Type": "application/json",
    }


@dataclass(frozen=True)
class Paid:
    payment_status: str
    verified: bool
    late_captured: bool
    provider_payment_id: str | None
    order_status: str
    line_status: str
    order_transitions: int
    line_transitions: int
    verified_audits: int
    late_audits: int
    outbox: int
    notifications: int


async def paid_state(engine: AsyncEngine, seeded: Seeded) -> Paid:
    sql = """
        SELECT p.status AS payment_status, p.verified_at IS NOT NULL AS verified,
          p.late_captured_at IS NOT NULL AS late_captured, p.provider_payment_id,
          o.status AS order_status,
          (SELECT fulfillment_status FROM order_items WHERE order_id = o.id) AS line_status,
          (SELECT count(*) FROM order_status_history WHERE order_id = o.id
             AND order_item_id IS NULL AND to_status = 'in_progress') AS order_transitions,
          (SELECT count(*) FROM order_status_history WHERE order_id = o.id
             AND order_item_id IS NOT NULL AND to_status = 'awaiting_delivery')
             AS line_transitions,
          (SELECT count(*) FROM audit_logs WHERE entity_id = p.id
             AND action = 'payment.verified') AS verified_audits,
          (SELECT count(*) FROM audit_logs WHERE entity_id = p.id
             AND action = 'payment.late_capture') AS late_audits,
          (SELECT count(*) FROM email_outbox WHERE template = 'order_payment_confirmed'
             AND payload->>'order_id' = CAST(o.id AS text)) AS outbox,
          (SELECT count(*) FROM notifications WHERE payload->>'event' = 'payment.confirmed'
             AND payload->>'order_id' = CAST(o.id AS text)) AS notifications
        FROM payments p JOIN orders o ON o.id = p.order_id WHERE p.id = :p
    """
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), {"p": seeded.payment_id})).one()
    return Paid(**row._mapping)


PAID_ONCE = {
    "payment_status": "paid",
    "verified": True,
    "late_captured": False,
    "order_status": "in_progress",
    "line_status": "awaiting_delivery",
    "order_transitions": 1,
    "line_transitions": 1,
    "verified_audits": 1,
    "late_audits": 0,
    "outbox": 1,
    "notifications": 1,
}


def paid_once(state: Paid) -> bool:
    return all(getattr(state, k) == v for k, v in PAID_ONCE.items())
