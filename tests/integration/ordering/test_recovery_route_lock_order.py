"""Lock order of the VS-024 routes, read from the SQL they send (plan 8.1): retry Tx1 takes
its own claim key, then the caller's `orders` row and no other existing row; the admin
reconcile request locks nothing, and its background Tx B starts with `orders`."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, csrf, login, mfa_admin
from tests.integration.ordering.test_lock_order import _TABLE, captured, locks, tables
from tests.integration.payments.recovery_support import YEARS_AHEAD, seed_attempt, seed_order
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _first_lock(statements: list[str]) -> int:
    return next(i for i, s in enumerate(statements) if "FOR UPDATE" in s)


async def test_retry_locks_its_claim_then_the_callers_order_and_nothing_else(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    placed = datetime.now(UTC) - timedelta(minutes=5)
    order = await seed_order(db_session, placed_at=placed, user_id=user.id)
    await seed_attempt(db_session, order, initiated_at=placed, status="failed")
    with client_for(main_app) as client:
        login(client, user.email)
        with captured(main_app.state.db_engine.sync_engine) as statements:
            response = client.post(
                f"/api/v1/me/orders/{order.order_id}/payments",
                json={},
                headers=csrf(client) | {"Idempotency-Key": f"lock-{uuid.uuid4().hex}"},
            )
    assert response.status_code == 201, response.text
    held = locks(statements)
    print("\nRETRY LOCKS", *(h[:120] for h in held), sep="\n  ")
    assert tables(held) == ["idempotency_records", "orders"]
    assert "ON CONFLICT ON CONSTRAINT uq_idempotency_records_scope_user_key DO NOTHING" in held[0]
    orders_lock = _first_lock(statements)
    assert statements[orders_lock].startswith("SELECT orders.id")
    assert "orders.user_id = " in statements[orders_lock]
    assert not any("FOR UPDATE" in s for s in statements[:orders_lock])
    writes = [_TABLE.findall(s)[0] for s in statements if s.startswith(("INSERT", "UPDATE"))]
    print("RETRY WRITES", writes)
    assert writes == [
        "idempotency_records",  # Tx1: the claim
        "payments",  # the attempt, in its SAVEPOINT
        "audit_logs",  # payment.retry_started
        "idempotency_records",  # resource_id; COMMIT, then the provider call
        "payments",  # Tx2: the provider reference
        "idempotency_records",  # done, with the stored 201
    ]
    savepoint = next(i for i, s in enumerate(statements) if s.startswith("SAVEPOINT"))
    insert = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO payments"))
    assert orders_lock < savepoint < insert


async def test_the_reconcile_request_locks_nothing_and_its_tx_b_starts_with_orders(
    db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = datetime(1600 + YEARS_AHEAD, 3, 1, tzinfo=UTC)
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, mock=mock, state="paid")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        with captured(main_app.state.db_engine.sync_engine) as statements:
            response = client.post(
                f"/api/v1/admin/payments/{payment_id}/reconcile", headers=csrf(client)
            )
    assert response.status_code == 202, response.text
    audit = next(
        i for i, s in enumerate(statements) if s.startswith("INSERT INTO audit_logs")
    )  # payment.reconcile_requested: the request's last statement before COMMIT
    request, background = statements[: audit + 1], statements[audit + 1 :]
    print("\nRECONCILE REQUEST", *(s[:110] for s in request), sep="\n  ")
    assert not any("FOR UPDATE" in s for s in request), request
    assert any(s.startswith("SELECT payments.id") for s in request)
    held = locks(background)
    print("RECONCILE BACKGROUND LOCKS", *(h[:110] for h in held), sep="\n  ")
    assert tables(held)[:3] == ["orders", "order_items", "payments"]
    first = _first_lock(background)
    assert not any("FOR UPDATE" in s for s in background[:first])
