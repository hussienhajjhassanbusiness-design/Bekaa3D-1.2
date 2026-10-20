"""VS-024 Tx B lock order, read from the SQL it sends (plan 8.1): one unlocked payments
read, then orders, lines by id and payments FOR UPDATE, and nothing else before them.
The captured amount is written in the same UPDATE as the status, after the three locks."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.payments.domain.outcome import ProviderResult
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import apply_provider_result, verify_event
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.test_payment_lock_order import writes
from tests.integration.payments.test_verification import _event, _factory
from tests.integration.payments.verification_support import (
    mock_fixture,  # noqa: F401
    pending_payment,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _before_first_write(statements: list[str]) -> list[str]:
    first = next(i for i, s in enumerate(statements) if s.startswith(("UPDATE", "INSERT")))
    return statements[:first]


def _assert_tx_b_prefix(statements: list[str]) -> None:
    reads = _before_first_write(statements)
    print("\nTX B before the first write:", *(s[:120] for s in reads), sep="\n  ")
    assert len(reads) == 4, reads
    assert reads[0].startswith("SELECT payments.id") and "FOR UPDATE" not in reads[0]
    assert reads[1].startswith("SELECT orders.id") and reads[1].endswith("FOR UPDATE")
    assert reads[2].startswith("SELECT order_items.id")
    assert reads[2].endswith("ORDER BY order_items.id FOR UPDATE")
    assert reads[3].startswith("SELECT payments.id") and reads[3].endswith("FOR UPDATE")


def _captured_writes(statements: list[str]) -> list[str]:
    return [s for s in statements if s.startswith("UPDATE payments") and "captured_amount" in s]


@pytest.mark.parametrize(
    ("result", "expired_first", "status_column"),
    [
        (ProviderResult("paid", 1000, "USD"), False, "status="),
        (ProviderResult("paid", 900, "USD"), False, "late_captured_at="),
        (ProviderResult("paid", 1000, "USD"), True, "late_captured_at="),
    ],
    ids=["paid", "live-mismatch", "after-expiry"],
)
async def test_tx_b_locks_first_and_writes_the_capture_with_the_status(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    result: ProviderResult,
    expired_first: bool,
    status_column: str,
) -> None:
    seeded = await pending_payment(db_session, mock)
    if expired_first:
        await db_session.execute(
            text("UPDATE payments SET status = 'expired', expired_at = now() WHERE id = :p"),
            {"p": seeded.payment_id},
        )
        await db_session.commit()
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await apply_provider_result(
                session, seeded.payment_id, result, source="webhook", actor_user_id=None
            )
    _assert_tx_b_prefix(statements)
    capture = _captured_writes(statements)
    print("  capture write:", *(s[:160] for s in capture))
    assert len(capture) == 1
    assert statements.index(capture[0]) == len(_before_first_write(statements))
    assert status_column in capture[0]
    assert writes(statements)[0] == "UPDATE payments"


async def test_the_webhook_path_has_the_same_prefix_and_marks_the_event_last(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid", 700)
    event_id = await _event(db_engine, seeded)
    with captured(db_engine.sync_engine) as statements:
        await verify_event(_factory(db_engine), {"mock": mock}, event_id)
    # Tx A: the event and the payment, unlocked; then Tx B from its first payments read.
    tx_a = statements[:2]
    assert not any("FOR UPDATE" in s for s in tx_a), tx_a
    _assert_tx_b_prefix(statements[2:])
    assert len(_captured_writes(statements)) == 1
    assert writes(statements)[-1] == "UPDATE webhook_events"
