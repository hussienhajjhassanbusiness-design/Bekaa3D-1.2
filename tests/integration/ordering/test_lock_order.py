"""The ADR-024 d9 / ADR-029 d4 lock order, read from the SQL each path really sends
(VS-023 plan 8.1): cart first (checkout only), then orders, lines by id, payments."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.main import app as main_app
from app.ordering.public import lock_order_for_change, mark_order_paid
from app.payments.domain.enums import PaymentProvider
from app.payments.infrastructure.payments import SqlPaymentStore
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import client_for, create_user
from tests.integration.ordering.checkout_support import (  # noqa: F401
    buyer,
    post_checkout,
    shop_open,
)
from tests.integration.payments.support import NOW, seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

_LOCK = re.compile(r"FOR UPDATE|ON CONFLICT", re.IGNORECASE)
_TABLE = re.compile(r"(?:\bFROM|\bINTO|^UPDATE)\s+(\w+)")


@contextmanager
def captured(engine: Engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def locks(statements: list[str]) -> list[str]:
    """`table: statement` for every row lock or unique-key wait, in order."""
    return [f"{_TABLE.findall(s)[0]}: {s}" for s in statements if _LOCK.search(s)]


def tables(entries: list[str]) -> list[str]:
    return [entry.split(":", 1)[0] for entry in entries]


async def test_checkout_locks_the_claim_key_then_the_cart_and_no_existing_order_row(
    db_session: AsyncSession,
) -> None:
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    with client_for(main_app) as client:
        await buyer(client, db_session, stl)
        with captured(main_app.state.db_engine.sync_engine) as statements:
            response = post_checkout(client)
    assert response.status_code == 201, response.text
    order = locks(statements)
    print("\nCHECKOUT", *order, sep="\n  ")
    assert tables(order) == ["idempotency_records", "carts"]
    assert "ON CONFLICT ON CONSTRAINT uq_idempotency_records_scope_user_key DO NOTHING" in order[0]
    assert order[1].endswith("WHERE carts.user_id = $1::UUID FOR UPDATE")
    writes = [s for s in statements if s.startswith(("INSERT", "UPDATE", "DELETE"))]
    print("CHECKOUT WRITES", *(w[:90] for w in writes), sep="\n  ")
    assert [_TABLE.findall(w)[0] for w in writes] == [
        "idempotency_records",
        "orders",
        "order_items",
        "payments",
        "order_status_history",
        "audit_logs",
        "cart_items",
        "carts",
        "idempotency_records",
        "payments",
        "idempotency_records",
    ]


async def test_payment_apply_locks_orders_then_lines_by_id_then_payments(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Tx B's prefix (`apply_provider_result`, step 12) and `mark_order_paid` under it."""
    user = await create_user(db_session)
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    order_id = await seed_online_order(db_session, user_id=user.id, stl_id=stl)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        payment = await SqlPaymentStore(session).insert_pending(
            order_id=order_id,
            provider=PaymentProvider.MOCK,
            amount_cents=1000,
            currency="USD",
            at=NOW,
        )
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            locked = await lock_order_for_change(session, order_id)
            assert locked is not None
            await SqlPaymentStore(session).lock(payment.id)
            before_mark = len(statements)
            await mark_order_paid(session, locked, at=datetime.now(UTC))
    order = locks(statements)
    print("\nAPPLY", *order, sep="\n  ")
    # VS-036 (ADR-044, plan 8.1): mark_order_paid's badge hook takes R_user (rank 7, advisory),
    # then the buyer's live reviews FOR UPDATE (rank 9), both after payments (rank 4). Its only
    # new locks; still no payments statement inside it.
    assert tables(order) == ["orders", "order_items", "payments", "reviews"]
    assert "ORDER BY order_items.id FOR UPDATE" in order[1]
    marked = statements[before_mark:]
    marked_locks = [s for s in marked if _LOCK.search(s) or "pg_advisory_xact_lock" in s]
    assert len(marked_locks) == 2, marked_locks
    assert "pg_advisory_xact_lock" in marked_locks[0]
    assert "FROM reviews" in marked_locks[1] and marked_locks[1].endswith("FOR UPDATE")
    assert not any("payments" in s for s in marked)


async def test_the_idempotency_purge_skips_locked_rows_and_touches_nothing_else(
    db_engine: AsyncEngine,
) -> None:
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await SqlIdempotencyStore(session).purge_expired(now=datetime.now(UTC), limit=10)
    print("\nPURGE", *statements, sep="\n  ")
    assert len(statements) == 1
    assert "FOR UPDATE SKIP LOCKED" in statements[0]
    assert set(_TABLE.findall(statements[0])) == {"idempotency_records"}
