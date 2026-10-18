"""VS-023 verification fixes for VS-024 (plan 3.2a, 3.3, 3.4): the bounded status query,
the manual-confirmation skip, `unknown` writing nothing, the captured amount taken only
from the provider's answer, and the admin actor recorded on the audit rows."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import app as main_app
from app.payments.application.ports import PaymentRef, ProviderStatus
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure import verification
from app.payments.infrastructure.providers.mock import MockPaymentProvider, _key
from app.payments.infrastructure.verification import (
    apply_provider_result,
    verify_event,
    verify_payment,
    verify_unprocessed,
)
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.test_verification import _event, _factory
from tests.integration.payments.verification_support import (
    WEBHOOK,
    Seeded,
    mock_fixture,  # noqa: F401
    pending_payment,
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

OPEN_TRANSACTIONS = """
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = current_database() AND pid <> pg_backend_pid()
      AND state LIKE 'idle in transaction%'
"""
# Everything `unknown` must leave untouched (plan 3.2a).
FROZEN = """
    SELECT p.status, p.failed_at, p.expired_at, p.verified_at, p.late_captured_at,
      p.captured_amount_cents, p.captured_currency, o.status AS order_status, o.cancelled_at,
      (SELECT array_agg(fulfillment_status ORDER BY id) FROM order_items
         WHERE order_id = o.id) AS lines,
      (SELECT count(*) FROM order_status_history WHERE order_id = o.id) AS history,
      (SELECT count(*) FROM audit_logs WHERE entity_id = p.id) AS audits
    FROM payments p JOIN orders o ON o.id = p.order_id WHERE p.id = :p
"""


class Hanging:
    """Answers nothing until the test lets it; records whether it was entered."""

    name = "mock"
    supports_status_query = True

    def __init__(self) -> None:
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        self.entered.set()
        await self.release.wait()
        return ProviderStatus(ProviderResult("pending", None, None), None)


class NoStatus:
    """A provider without a status API (VS-032 may ship one): it must never be asked."""

    name = "mock"
    supports_status_query = False

    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    async def query_status(self, ref: PaymentRef) -> ProviderStatus:
        self.calls.append(ref.payment_id)
        raise AssertionError("a provider without a status API was queried")


async def _row(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def _event_state(engine: AsyncEngine, event_id: uuid.UUID) -> Any:
    return await _row(
        engine,
        "SELECT processed_at, processing_error FROM webhook_events WHERE id = :e",
        e=event_id,
    )


async def _forget(seeded: Seeded) -> None:
    """The mock loses the payment (never created, or its state expired): `unknown`."""
    client = redis.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    try:
        await client.delete(_key(seeded.payment_id))
    finally:
        await client.aclose()


async def _old_event(engine: AsyncEngine, seeded: Seeded, received_at: datetime) -> uuid.UUID:
    event_id = await _event(engine, seeded)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE webhook_events SET received_at = :t WHERE id = :e"),
            {"t": received_at, "e": event_id},
        )
    return event_id


# --- The 10 s bound on the status query (plan 3.3) ---------------------------------


async def test_a_hanging_status_query_is_cut_with_no_transaction_open(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verification, "PROVIDER_TIMEOUT_SECONDS", 0.5)
    seeded = await pending_payment(db_session, mock)
    event_id = await _event(db_engine, seeded)
    hanging = Hanging()
    task = asyncio.create_task(verify_event(_factory(db_engine), {"mock": hanging}, event_id))  # type: ignore[dict-item]
    await asyncio.wait_for(hanging.entered.wait(), 5)
    async with db_engine.connect() as conn:
        open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
    # Without the bound this never returns: the outer wait turns the hang into a failure.
    assert await asyncio.wait_for(task, 5) is None
    assert open_during_call == 0
    event = await _event_state(db_engine, event_id)
    assert event.processed_at is None and "timed out" in event.processing_error
    assert (await _row(db_engine, FROZEN, p=seeded.payment_id)).status == "pending"


async def test_a_hanging_status_query_defers_reconciliation(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verification, "PROVIDER_TIMEOUT_SECONDS", 0.5)
    seeded = await pending_payment(db_session, mock)
    hanging = Hanging()
    with pytest.raises(ProviderUnavailableError, match="timed out"):
        await asyncio.wait_for(
            verify_payment(_factory(db_engine), {"mock": hanging}, seeded.payment_id),  # type: ignore[dict-item]
            5,
        )
    assert hanging.entered.is_set()
    assert (await _row(db_engine, FROZEN, p=seeded.payment_id)).status == "pending"


# --- A provider without a status API: manual confirmation (plan 3.3) ---------------


async def test_an_event_for_a_no_status_provider_is_never_queried_and_stays_unprocessed(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)
    stub = NoStatus()
    before = await _row(db_engine, FROZEN, p=seeded.payment_id)
    for _ in range(2):
        assert await verify_event(_factory(db_engine), {"mock": stub}, event_id) is None  # type: ignore[dict-item]
    assert stub.calls == []
    event = await _event_state(db_engine, event_id)
    assert (event.processed_at, event.processing_error) == (None, "manual_confirmation_required")
    assert await _row(db_engine, FROZEN, p=seeded.payment_id) == before


async def test_verify_payments_skips_events_awaiting_manual_confirmation(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """The oldest event awaits manual confirmation; it must not block the one behind it."""
    awaiting = await pending_payment(db_session, mock)
    behind = await pending_payment(db_session, mock)
    head = await _old_event(db_engine, awaiting, datetime(1990, 1, 1, tzinfo=UTC))
    assert await verify_event(_factory(db_engine), {"mock": NoStatus()}, head) is None  # type: ignore[dict-item]
    second = await _old_event(db_engine, behind, datetime(1990, 1, 2, tzinfo=UTC))
    async with async_sessionmaker(db_engine)() as session:
        oldest = await SqlWebhookEventStore(session).unprocessed_ids(1)
    assert oldest == [second]
    counts = await verify_unprocessed(_factory(db_engine), {"mock": mock}, limit=1)
    assert counts == {"seen": 1, "applied": 1, "deferred": 0}
    assert (await _event_state(db_engine, second)).processed_at is not None
    assert (await _event_state(db_engine, head)).processing_error == (
        "manual_confirmation_required"
    )


# --- `unknown` writes nothing (plan 3.2a) --------------------------------------------


async def test_an_unknown_answer_to_an_event_moves_nothing_and_keeps_it_unprocessed(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    event_id = await _event(db_engine, seeded)
    await _forget(seeded)
    before = await _row(db_engine, FROZEN, p=seeded.payment_id)
    assert await verify_event(_factory(db_engine), {"mock": mock}, event_id) is None
    assert await _row(db_engine, FROZEN, p=seeded.payment_id) == before
    event = await _event_state(db_engine, event_id)
    assert (event.processed_at, event.processing_error) == (None, "provider_unknown_reference")


async def test_an_unknown_answer_to_reconciliation_opens_no_tx_b(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock, store_reference=False)
    await _forget(seeded)
    before = await _row(db_engine, FROZEN, p=seeded.payment_id)
    with captured(db_engine.sync_engine) as statements:
        outcome = await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id)
    assert outcome is Outcome.NOOP
    assert not any("FOR UPDATE" in s for s in statements), statements
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in statements), statements
    assert await _row(db_engine, FROZEN, p=seeded.payment_id) == before


# --- The captured amount: only the provider's answer, under the locks (plan 3.4) -----


async def test_paid_stores_the_providers_captured_amount(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock, total_cents=1250)
    await mock.simulate(seeded.payment_id, "paid")
    assert await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id) is (
        Outcome.APPLY_PAID
    )
    row = await _row(db_engine, FROZEN, p=seeded.payment_id)
    assert (row.status, row.captured_amount_cents, row.captured_currency) == ("paid", 1250, "USD")


@pytest.mark.parametrize(
    ("captured_cents", "currency"),
    [(900, None), (1100, None), (1000, "EUR")],
    ids=["underpaid", "overpaid", "wrong-currency"],
)
async def test_a_late_capture_stores_what_the_provider_captured(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    captured_cents: int,
    currency: str | None,
) -> None:
    seeded = await pending_payment(db_session, mock, total_cents=1000)
    await mock.simulate(seeded.payment_id, "paid", captured_cents, currency=currency)
    assert await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id) is (
        Outcome.LATE_CAPTURE_AND_FAIL
    )
    row = await _row(db_engine, FROZEN, p=seeded.payment_id)
    assert row.late_captured_at is not None
    assert (row.captured_amount_cents, row.captured_currency) == (captured_cents, currency or "USD")


async def test_the_webhook_body_never_supplies_the_captured_amount(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """The body claims a paid 1 EUR; the provider's own answer (1000 USD) is what is stored."""
    seeded = await pending_payment(db_session, mock, total_cents=1000)
    await mock.simulate(seeded.payment_id, "paid")
    body = _claiming(seeded, status="paid", captured_amount_cents=1, currency="EUR", amount=1)
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    row = await _row(db_engine, FROZEN, p=seeded.payment_id)
    assert (row.status, row.captured_amount_cents, row.captured_currency) == ("paid", 1000, "USD")


async def test_a_webhook_claiming_paid_captures_nothing_while_the_provider_says_pending(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    body = _claiming(seeded, status="paid", captured_amount_cents=1000, currency="USD")
    with client_for(main_app) as client:
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 200
    row = await _row(db_engine, FROZEN, p=seeded.payment_id)
    assert (row.status, row.late_captured_at, row.captured_amount_cents) == ("pending", None, None)


def _claiming(seeded: Seeded, **claim: Any) -> bytes:
    """A signed-able mock event for the payment that also claims an outcome and amount."""
    return json.dumps(
        {
            "event_id": f"ev_{uuid.uuid4().hex}",
            "type": "payment",
            "payment_reference": str(seeded.payment_id),
            "provider_payment_id": seeded.reference,
            **claim,
        }
    ).encode()


# --- The actor (plan 3.4: today every apply audit row has a NULL actor) --------------


@pytest.mark.parametrize(
    ("answer", "action"),
    [
        (ProviderResult("paid", 1000, "USD"), "payment.verified"),
        (ProviderResult("failed", None, None), "payment.failed"),
        (ProviderResult("paid", 900, "USD"), "payment.late_capture"),
    ],
    ids=["paid", "failed", "late-capture"],
)
async def test_an_admin_apply_records_the_admin_as_actor(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    answer: ProviderResult,
    action: str,
) -> None:
    seeded = await pending_payment(db_session, mock)
    admin = await create_user(db_session)
    await db_session.commit()
    async with async_sessionmaker(db_engine)() as session, session.begin():
        await apply_provider_result(
            session, seeded.payment_id, answer, source="manual", actor_user_id=admin.id
        )
    audit = await _row(
        db_engine,
        "SELECT actor_user_id, after_data->>'source' AS source FROM audit_logs"
        " WHERE entity_id = :p AND action = :a",
        p=seeded.payment_id,
        a=action,
    )
    assert (audit.actor_user_id, audit.source) == (admin.id, "manual")


async def test_a_job_apply_records_no_actor(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id, source="release")
    audit = await _row(
        db_engine,
        "SELECT actor_user_id, after_data->>'source' AS source FROM audit_logs"
        " WHERE entity_id = :p AND action = 'payment.verified'",
        p=seeded.payment_id,
    )
    assert (audit.actor_user_id, audit.source) == (None, "release")
