"""Verification against Postgres and the mock (VS-023 plan 2.4, 3.6, 6.2): the provider's
own answer decides; paid only on the exact amount in USD; anything else that captured
money is a late capture, recorded once."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.verify_payments import verify_payments
from app.payments.application.ports import NewWebhookEvent
from app.payments.domain.enums import PaymentProvider
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import verify_event, verify_payment
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.payments.verification_support import (
    PAID_ONCE,
    Seeded,
    mock_fixture,  # noqa: F401
    paid_once,
    paid_state,
    pending_payment,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

LATE = "SELECT id FROM payments WHERE late_captured_at IS NOT NULL ORDER BY late_captured_at"


async def _event(engine: AsyncEngine, seeded: Seeded) -> uuid.UUID:
    """An unprocessed event for the payment, as the webhook stores it."""
    async with async_sessionmaker(engine)() as session, session.begin():
        event_id = await SqlWebhookEventStore(session).insert_if_new(
            NewWebhookEvent(
                provider=PaymentProvider.MOCK,
                provider_event_id=f"ev_{uuid.uuid4().hex}",
                event_type="payment",
                payload={"payment_reference": str(seeded.payment_id)},
                signature_valid=True,
                provider_payment_id=seeded.reference,
                payment_id=seeded.payment_id,
                processing_error=None,
                processed_at=None,
            )
        )
    assert event_id is not None
    return event_id


def _factory(engine: AsyncEngine) -> Any:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _late_audit(engine: AsyncEngine, seeded: Seeded) -> dict[str, Any]:
    async with engine.connect() as conn:
        data: dict[str, Any] = await conn.scalar(
            text(
                "SELECT after_data FROM audit_logs WHERE entity_id = :p"
                " AND action = 'payment.late_capture'"
            ),
            {"p": seeded.payment_id},
        )
    return data


async def test_a_paid_answer_marks_the_payment_and_moves_the_stl_line(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    outcome = await verify_event(
        _factory(db_engine), {"mock": mock}, await _event(db_engine, seeded)
    )
    assert outcome is Outcome.APPLY_PAID
    state = await paid_state(db_engine, seeded)
    assert paid_once(state), state
    async with db_engine.connect() as conn:
        outbox = (
            await conn.execute(
                text(
                    "SELECT recipient_email, payload FROM email_outbox"
                    " WHERE template = 'order_payment_confirmed' AND payload->>'order_id' = :o"
                ),
                {"o": str(seeded.order_id)},
            )
        ).one()
        history = (
            await conn.execute(
                text(
                    "SELECT from_status, to_status, order_item_id IS NULL AS order_row"
                    " FROM order_status_history WHERE order_id = :o ORDER BY created_at, id"
                ),
                {"o": seeded.order_id},
            )
        ).all()
    assert outbox.recipient_email == "buyer@example.com"  # the checkout-time snapshot
    assert sorted((h.from_status, h.to_status, h.order_row) for h in history) == [
        ("pending", "awaiting_delivery", False),
        ("pending_payment", "in_progress", True),
    ]


async def test_the_kill_switch_does_not_block_an_in_flight_payment(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    async with db_engine.connect() as conn:
        assert (
            await conn.scalar(text("SELECT value FROM settings WHERE key = 'accepting_orders'"))
            is False
        )
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    assert await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id) is (
        Outcome.APPLY_PAID
    )


@pytest.mark.parametrize(
    ("captured", "currency"),
    [(900, None), (1100, None), (1000, "EUR")],
    ids=["underpaid", "overpaid", "wrong-currency"],
)
async def test_a_capture_that_does_not_match_exactly_is_a_late_capture(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    captured: int,
    currency: str | None,
) -> None:
    seeded = await pending_payment(db_session, mock, total_cents=1000)
    await mock.simulate(seeded.payment_id, "paid", captured, currency=currency)
    outcome = await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id)
    assert outcome is Outcome.LATE_CAPTURE_AND_FAIL
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.verified, state.late_captured) == ("failed", False, True)
    assert (state.line_status, state.order_status, state.late_audits) == (
        "pending",
        "pending_payment",
        1,
    )
    audit = await _late_audit(db_engine, seeded)
    assert audit["reason"] == "amount_mismatch"
    assert (audit["captured_amount_cents"], audit["expected_amount_cents"]) == (captured, 1000)
    async with db_engine.connect() as conn:
        assert seeded.payment_id in {row.id for row in await conn.execute(text(LATE))}


async def test_a_success_on_a_cancelled_order_is_a_late_capture(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await db_session.execute(
        text("UPDATE orders SET status = 'cancelled', cancelled_at = now() WHERE id = :o"),
        {"o": seeded.order_id},
    )
    await db_session.commit()
    await mock.simulate(seeded.payment_id, "paid")
    outcome = await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id)
    assert outcome is Outcome.LATE_CAPTURE_AND_FAIL
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.line_status, state.late_audits) == ("failed", "pending", 1)
    assert (await _late_audit(db_engine, seeded))["reason"] == "order_cancelled"


async def test_a_success_after_expiry_is_recorded_once(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    providers = {"mock": mock}
    await mock.simulate(seeded.payment_id, "expired")
    assert await verify_payment(_factory(db_engine), providers, seeded.payment_id) is (
        Outcome.MARK_EXPIRED
    )
    await mock.simulate(seeded.payment_id, "paid")
    first = await verify_payment(_factory(db_engine), providers, seeded.payment_id)
    again = await verify_payment(_factory(db_engine), providers, seeded.payment_id)
    assert (first, again) == (Outcome.LATE_CAPTURE, Outcome.NOOP)
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.late_captured, state.late_audits) == ("expired", True, 1)
    assert state.line_status == "pending"
    assert (await _late_audit(db_engine, seeded))["reason"] == "attempt_not_live"


@pytest.mark.parametrize(
    ("answer", "outcome", "status"),
    [
        ("failed", Outcome.MARK_FAILED, "failed"),
        ("expired", Outcome.MARK_EXPIRED, "expired"),
        ("processing", Outcome.MARK_PROCESSING, "processing"),
    ],
)
async def test_an_unpaid_answer_leaves_the_order_awaiting_payment(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    answer: str,
    outcome: Outcome,
    status: str,
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, answer)  # type: ignore[arg-type]
    assert await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id) is outcome
    state = await paid_state(db_engine, seeded)
    assert (state.payment_status, state.order_status, state.line_status) == (
        status,
        "pending_payment",
        "pending",
    )


async def test_a_provider_timeout_defers_the_event_to_the_next_run(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)

    class Down:
        async def query_status(self, ref: Any) -> Any:
            raise ProviderUnavailableError("timed out")

    assert await verify_event(_factory(db_engine), {"mock": Down()}, event_id) is None  # type: ignore[dict-item]
    async with db_engine.connect() as conn:
        deferred = (
            await conn.execute(
                text("SELECT processed_at, processing_error FROM webhook_events WHERE id = :e"),
                {"e": event_id},
            )
        ).one()
    assert (deferred.processed_at, deferred.processing_error) == (None, "timed out")
    assert (await paid_state(db_engine, seeded)).payment_status == "pending"

    ctx = {"session_factory": _factory(db_engine), "payment_providers": {"mock": mock}}
    await verify_payments(ctx)
    assert paid_once(await paid_state(db_engine, seeded))


async def test_the_cron_applies_an_event_whose_background_task_was_lost(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock)
    await mock.simulate(seeded.payment_id, "paid")
    event_id = await _event(db_engine, seeded)
    started = datetime.now(UTC)
    ctx = {"session_factory": _factory(db_engine), "payment_providers": {"mock": mock}}
    counts = await verify_payments(ctx)
    elapsed = (datetime.now(UTC) - started).total_seconds()
    assert counts["applied"] >= 1
    assert paid_once(await paid_state(db_engine, seeded))
    async with db_engine.connect() as conn:
        assert await conn.scalar(
            text("SELECT processed_at IS NOT NULL FROM webhook_events WHERE id = :e"),
            {"e": event_id},
        )
    print(f"\ncron tick applied the event in {elapsed:.3f}s")


async def test_the_missing_provider_reference_is_stored_when_applying(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    seeded = await pending_payment(db_session, mock, store_reference=False)
    await mock.simulate(seeded.payment_id, "paid")
    assert await verify_payment(_factory(db_engine), {"mock": mock}, seeded.payment_id) is (
        Outcome.APPLY_PAID
    )
    state = await paid_state(db_engine, seeded)
    assert state.provider_payment_id == seeded.reference
    assert {k: getattr(state, k) for k in PAID_ONCE} == PAID_ONCE
