"""Seeding for VS-024 recovery tests: orders placed at a chosen time, attempts in any
state, known (or not) to the mock. Each test picks its own far-past epoch, and the jobs
are run from that epoch's keyset start, so rows other tests leave behind never match."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.identity.domain.enums import UserRole
from app.identity.public import active_administrator_contacts
from app.payments.application.ports import CreatePayment, PaymentRef, ProviderStatus
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

HOLD = timedelta(seconds=1800)  # the checkout_hold_period default
# Each test's epoch is its year plus this: after `NOW` and past every far-past window
# (1985, 1990, 1991) that older tests read without a lower bound.
YEARS_AHEAD = 300
START = uuid.UUID(int=0)


@dataclass(frozen=True)
class SeededOrder:
    order_id: uuid.UUID
    user_id: uuid.UUID
    stl_id: uuid.UUID
    order_number: str
    placed_at: datetime


def keyset_start(epoch: datetime) -> tuple[datetime, uuid.UUID]:
    """Just before `epoch`, so a job run sees this test's rows and none older."""
    return (epoch - timedelta(microseconds=1), START)


async def _insert(db: AsyncSession, table: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    values = ", ".join(
        f"CAST(:{k} AS jsonb)" if k in {"provider_metadata", "payload"} else f":{k}" for k in row
    )
    await db.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({values})"), row)


async def seed_order(
    db: AsyncSession,
    *,
    placed_at: datetime,
    total_cents: int = 1000,
    physical: bool = False,
    user_id: uuid.UUID | None = None,
    stl_id: uuid.UUID | None = None,
    with_lines: bool = True,
    stl: bool = True,
    **over: Any,
) -> SeededOrder:
    """An unpaid online order with one STL line (plus one physical line when asked);
    `stl=False` leaves only the physical line (a seeded cash order)."""
    if user_id is None:
        user_id = (await create_user(db)).id
    refs = await seed_refs(db) if stl_id is None or physical else None
    if stl_id is None:
        assert refs is not None
        stl_id = (await seed_product(db, refs, type=ProductType.STL)).id
    order_id, number = uuid.uuid4(), f"B3D-{uuid.uuid4().hex[:8].upper()}"
    lines_total = (total_cents if stl else 0) + (2000 if physical else 0)
    order: dict[str, Any] = {
        "id": order_id,
        "order_number": number,
        "user_id": user_id,
        "customer_email_snapshot": "buyer@example.com",
        "source": "cart",
        "status": "pending_payment",
        "payment_method": "online",
        "subtotal_cents": lines_total,
        "total_cents": lines_total,
        "terms_accepted_at": placed_at,
        "digital_terms_accepted_at": placed_at,
        "digital_terms_version": "2026-10-17",
        "placed_at": placed_at,
    }
    if physical:
        order |= {
            "fulfillment_method": "pickup",
            "contact_phone_snapshot": "+96170123456",
            "contact_phone_hash": "a" * 64,
        }
    await _insert(db, "orders", order | over)
    line = {
        "order_id": order_id,
        "user_id": user_id,
        "payment_method": (order | over)["payment_method"],
        "product_type": "stl",
        "product_name_snapshot": "Seeded STL",
        "quantity": 1,
        "fulfillment_status": "pending",
    }
    if with_lines and stl:
        await _insert(
            db,
            "order_items",
            line
            | {
                "product_id": stl_id,
                "unit_price_cents": total_cents,
                "line_total_cents": total_cents,
            },
        )
    if physical and with_lines:
        assert refs is not None
        lamp = (await seed_product(db, refs)).id
        await _insert(
            db,
            "order_items",
            line
            | {
                "product_id": lamp,
                "product_type": "physical",
                "product_name_snapshot": "Lamp",
                "unit_price_cents": 1000,
                "quantity": 2,
                "line_total_cents": 2000,
                "lead_time_days_snapshot": 3,
                "batch_size_snapshot": 2,
                "accepted_payment_methods_snapshot": "online_or_cash",
            },
        )
    await db.commit()
    return SeededOrder(order_id, user_id, stl_id, number, placed_at)


async def seed_attempt(
    db: AsyncSession,
    order: SeededOrder,
    *,
    initiated_at: datetime,
    status: str = "pending",
    mock: MockPaymentProvider | None = None,
    state: str | None = None,
    amount_cents: int | None = None,
    reference: bool = True,
    provider: str = "mock",
) -> uuid.UUID:
    """One attempt; with `mock`, the mock knows it (pending, or `state` when given)."""
    payment_id = uuid.uuid4()
    amount = amount_cents if amount_cents is not None else await _total(db, order.order_id)
    provider_reference = None
    if mock is not None:
        created = await mock.create_payment(
            CreatePayment(payment_id, order.order_number, amount, "USD", "")
        )
        provider_reference = created.provider_payment_id if reference else None
        if state is not None:
            await mock.simulate(payment_id, state)  # type: ignore[arg-type]
    row: dict[str, Any] = {
        "id": payment_id,
        "order_id": order.order_id,
        "provider": provider,
        "order_payment_method": "online",
        "status": status,
        "amount_cents": amount,
        "initiated_at": initiated_at,
        "provider_payment_id": provider_reference,
    }
    stamp = {"failed": "failed_at", "expired": "expired_at", "paid": "verified_at"}.get(status)
    if stamp:
        row[stamp] = initiated_at
    await _insert(db, "payments", row)
    await db.commit()
    return payment_id


async def seed_event(
    db: AsyncSession, payment_id: uuid.UUID, *, received_at: datetime
) -> uuid.UUID:
    """An unprocessed, signature-valid webhook event for the payment."""
    event_id = uuid.uuid4()
    await _insert(
        db,
        "webhook_events",
        {
            "id": event_id,
            "provider": "mock",
            "provider_event_id": f"ev_{uuid.uuid4().hex}",
            "event_type": "payment",
            "payload": "{}",
            "signature_valid": True,
            "payment_id": payment_id,
            "received_at": received_at,
        },
    )
    await db.commit()
    return event_id


async def _total(db: AsyncSession, order_id: uuid.UUID) -> int:
    total: int = await db.scalar(
        text("SELECT total_cents FROM orders WHERE id = :o"), {"o": order_id}
    )
    return total


async def one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


ORDER_STATE = """
    SELECT o.status, o.cancelled_at,
      (SELECT array_agg(fulfillment_status::text ORDER BY id) FROM order_items
         WHERE order_id = o.id) AS lines,
      (SELECT bool_and(cancelled_at IS NOT NULL) FROM order_items
         WHERE order_id = o.id AND fulfillment_status = 'cancelled') AS lines_stamped,
      (SELECT count(*) FROM order_status_history WHERE order_id = o.id) AS history,
      (SELECT count(*) FROM audit_logs WHERE entity_id = o.id
         AND action = 'order.checkout_released') AS released_audits,
      (SELECT count(*) FROM notifications WHERE user_id = o.user_id
         AND payload->>'event' = 'order.checkout_expired'
         AND payload->>'order_id' = CAST(o.id AS text)) AS notices,
      (SELECT count(*) FROM email_outbox WHERE template = 'order_checkout_expired'
         AND payload->>'order_id' = CAST(o.id AS text)) AS emails
    FROM orders o WHERE o.id = :o
"""
PAYMENT_STATE = """
    SELECT status, late_captured_at, captured_amount_cents, captured_currency,
      provider_payment_id
    FROM payments WHERE id = :p
"""
# Everything but alert rows: what "nothing written" compares (plan 6.2).
UNTOUCHED = """
    SELECT o.status, o.cancelled_at, o.updated_at,
      (SELECT array_agg(row(i.fulfillment_status::text, i.cancelled_at, i.updated_at)::text
         ORDER BY i.id) FROM order_items i WHERE i.order_id = o.id) AS lines,
      (SELECT array_agg(row(p.status::text, p.provider_payment_id, p.failed_at, p.expired_at,
         p.verified_at, p.late_captured_at, p.captured_amount_cents, p.updated_at)::text
         ORDER BY p.id) FROM payments p WHERE p.order_id = o.id) AS payments,
      (SELECT count(*) FROM order_status_history h WHERE h.order_id = o.id) AS history,
      (SELECT count(*) FROM audit_logs a WHERE a.action <> 'payment.alert_raised'
         AND (a.entity_id = o.id
              OR a.entity_id IN (SELECT id FROM payments WHERE order_id = o.id))) AS audits,
      (SELECT count(*) FROM email_outbox e WHERE e.payload->>'order_id' = CAST(o.id AS text)
         AND e.template <> 'admin_payment_alert') AS emails
    FROM orders o WHERE o.id = :o
"""


class Spy:
    """The mock, counting the status queries it answers."""

    name = "mock"
    supports_status_query = True

    def __init__(self, mock: MockPaymentProvider) -> None:
        self.mock, self.calls = mock, 0

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        self.calls += 1
        return await self.mock.query_status(ref)


class Down:
    """A status provider that never answers."""

    name = "mock"
    supports_status_query = True

    def __init__(self) -> None:
        self.calls = 0

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        self.calls += 1
        raise ProviderUnavailableError("connection refused")


def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def alerts(engine: AsyncEngine, payment_id: uuid.UUID) -> dict[str, int]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT after_data->>'kind' AS kind, count(*) AS n FROM audit_logs"
                " WHERE entity_id = :p AND action = 'payment.alert_raised' GROUP BY 1"
            ),
            {"p": payment_id},
        )
        return {row.kind: row.n for row in rows}


async def provider_alerts(engine: AsyncEngine, provider: str = "mock") -> int:
    async with engine.connect() as conn:
        count: int = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
                " AND entity_id IS NULL AND after_data->>'kind' = 'provider_unreachable'"
                " AND after_data->>'provider' = :v AND created_at > now() - interval '1 hour'"
            ),
            {"v": provider},
        )
        return count


async def forget_provider_alerts(engine: AsyncEngine) -> None:
    """Age every recent `provider_unreachable` row out of its 1 h window (shared database)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE audit_logs SET created_at = created_at - interval '2 hours'"
                " WHERE action = 'payment.alert_raised' AND entity_id IS NULL"
                " AND after_data->>'kind' = 'provider_unreachable'"
                " AND created_at > now() - interval '2 hours'"
            )
        )


async def admin(db: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """At least one verified admin; everyone an alert reaches."""
    await create_user(db, role=UserRole.ADMIN)
    contacts = await active_administrator_contacts(db)
    await db.commit()
    return contacts


async def explain(engine: AsyncEngine, query: Any, *, seqscan: bool) -> str:
    """EXPLAIN the store's own Select with its parameters, on fresh statistics (as
    autovacuum keeps them); `seqscan=False` disables seq scans."""
    compiled = query.compile(compile_kwargs={"render_postcompile": True})
    async with engine.connect() as conn:
        await conn.execute(text("ANALYZE payments, orders"))
        await conn.commit()
        if not seqscan:
            await conn.execute(text("SET enable_seqscan = off"))
        rows = await conn.execute(text(f"EXPLAIN {compiled}"), dict(compiled.params))
        plan = "\n".join(str(row[0]) for row in rows)
        await conn.rollback()
    return plan


@pytest_asyncio.fixture
async def drop_alert_emails(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """After the test, delete the admin alert emails it queued (only VS-024 writes this
    template), so the shared outbox never carries thousands of them into later tests."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM email_outbox WHERE template = 'admin_payment_alert'"))
