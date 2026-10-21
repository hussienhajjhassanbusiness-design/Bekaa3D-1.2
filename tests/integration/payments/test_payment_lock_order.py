"""Payment paths' locks, read from the SQL they send (VS-023 plan 8.1; ADR-024 d9):
receipt and Tx A lock nothing; Tx B locks orders, lines by id, payments and, once an STL is
paid, the (user, product) advisory lock and its live offers (ADR-037); the event goes last."""

import re
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.identity.public import active_administrator_contacts
from app.main import app as main_app
from app.payments.domain.outcome import ProviderResult
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import apply_provider_result, verify_event
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user
from tests.integration.ordering.test_lock_order import captured, locks, tables
from tests.integration.payments.test_verification import _event
from tests.integration.payments.verification_support import (
    WEBHOOK,
    event_body,
    mock_fixture,  # noqa: F401
    pending_payment,
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
_WRITE = re.compile(r"^(INSERT INTO|UPDATE|DELETE FROM) (\w+)")
# VS-024 3.5: the late-capture alert's audit row, then a notification and an email per admin.
ALERT = "alert"


def writes(statements: list[str]) -> list[str]:
    return [f"{m.group(1).split()[0]} {m.group(2)}" for s in statements if (m := _WRITE.match(s))]


@pytest.mark.parametrize(
    ("result", "expected_writes"),
    [
        (
            ProviderResult("paid", 1000, "USD"),
            [
                "UPDATE payments",
                "UPDATE order_items",
                "INSERT order_status_history",
                "UPDATE orders",
                "INSERT order_status_history",
                "INSERT audit_logs",
                "INSERT email_outbox",
                "INSERT notifications",
            ],
        ),
        (ProviderResult("expired", None, None), ["UPDATE payments", "INSERT audit_logs"]),
        (
            ProviderResult("paid", 900, "USD"),
            ["UPDATE payments", "INSERT audit_logs", ALERT],
        ),
    ],
    ids=["paid", "expiry", "late-capture"],
)
async def test_apply_locks_orders_then_lines_then_payments_and_nothing_else(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    result: ProviderResult,
    expected_writes: list[str],
) -> None:
    seeded = await pending_payment(db_session, mock)
    await create_user(db_session, role=UserRole.ADMIN)
    admins = len(await active_administrator_contacts(db_session))
    await db_session.commit()
    alert = ["INSERT audit_logs", *["INSERT notifications", "INSERT email_outbox"] * admins]
    expected_writes = [w for e in expected_writes for w in (alert if e == ALERT else [e])]
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await apply_provider_result(
                session, seeded.payment_id, result, source="reconcile", actor_user_id=None
            )
    order = locks(statements)
    print(f"\nAPPLY {result.state}/{result.captured_amount_cents}", *order, sep="\n  ")
    print("  writes:", writes(statements))
    paid = writes(statements)[1:2] == ["UPDATE order_items"]
    assert tables(order) == ["orders", "order_items", "payments", *(["offers"] if paid else [])]
    assert order[1].endswith("ORDER BY order_items.id FOR UPDATE")
    assert writes(statements) == expected_writes
    if paid:
        assert_acquisition_lock_between_payments_and_offers(statements)


def assert_acquisition_lock_between_payments_and_offers(statements: list[str]) -> None:
    """ADR-037: the advisory lock after the payment row and before any offer row."""
    at = [i for i, s in enumerate(statements) if "pg_advisory_xact_lock" in s]
    payment = max(
        i for i, s in enumerate(statements) if s.endswith("FOR UPDATE") and "FROM payments" in s
    )
    offer = next(
        i for i, s in enumerate(statements) if s.endswith("FOR UPDATE") and "FROM offers" in s
    )
    assert len(at) == 1 and payment < at[0] < offer


async def test_receipt_and_tx_a_lock_nothing_and_the_event_is_processed_last(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    body = event_body(seeded)
    with client_for(main_app) as client:
        engine: Any = main_app.state.db_engine.sync_engine
        with captured(engine) as receipt:
            # Mock still pending: verification applies nothing, so receipt is isolated.
            assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    receipt_locks = locks(receipt)
    print("\nRECEIPT+BACKGROUND", *receipt_locks, sep="\n  ")
    assert receipt_locks[0].startswith("webhook_events: INSERT INTO webhook_events")
    assert (
        "ON CONFLICT ON CONSTRAINT uq_webhook_events_provider_event DO NOTHING" in receipt_locks[0]
    )

    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)
    with captured(db_engine.sync_engine) as verification:
        await verify_event(async_sessionmaker(db_engine), {"mock": mock}, event_id)
    order = locks(verification)
    print("VERIFY", *order, sep="\n  ")
    assert tables(order) == ["orders", "order_items", "payments", "offers"]
    assert_acquisition_lock_between_payments_and_offers(verification)
    first_lock = next(i for i, s in enumerate(verification) if "FOR UPDATE" in s)
    assert not any("FOR UPDATE" in s for s in verification[:first_lock]), "Tx A locks nothing"
    assert writes(verification)[-1] == "UPDATE webhook_events"
