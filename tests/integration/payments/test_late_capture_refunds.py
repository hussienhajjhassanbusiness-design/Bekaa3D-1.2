"""I15 (VS-030 plan 3.5, 6.2; D10, Q6, Q7): a late capture leaves exactly one `late_capture`
refund obligation for what was captured, and the admin settles, fails, reissues or voids it
although the order was never paid. Late captures never move an order or payment status."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.main import app as main_app
from app.payments.domain.enums import PaymentProvider, RefundKind
from app.payments.domain.outcome import Outcome
from app.payments.domain.refunds import BAD_CURRENCY_NOTE, NO_AMOUNT_NOTE, NewRefund
from app.payments.infrastructure.refunds import SqlRefundStore
from tests.integration.deep_support import client_for, mfa_admin
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import (
    act,
    attempt,
    count,
    create,
    late_capture,
    late_refunds,
    ok,
    paid_online,
    payment_of,
    queue_ids,
    statuses,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

NOTICES = (
    "SELECT count(*) FROM email_outbox WHERE template = 'order_refund_issued'"
    " AND payload->>'refund_id' = :r"
)


async def _expired_order(engine: AsyncEngine, db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """An online order whose only attempt expired unpaid: (order id, payment id)."""
    order = await seed_physical_order(db, payment_method="online", payment_status="expired")
    return order.order_id, await payment_of(engine, order.order_id)


async def _state(engine: AsyncEngine, table: str, row_id: uuid.UUID) -> str:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text(f"SELECT status::text FROM {table} WHERE id = :i"), {"i": row_id}
        )
    return str(found)


async def test_i15_a_late_success_after_expiry_leaves_one_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id, payment_id = await _expired_order(db_engine, db_session)
    assert await late_capture(db_engine, payment_id, 1000) is Outcome.LATE_CAPTURE
    assert await late_capture(db_engine, payment_id, 1000) is Outcome.NOOP  # a second event
    (row,) = await late_refunds(db_engine, payment_id)
    assert (row.status, row.amount_cents, row.currency) == ("pending", 1000, "USD")
    assert (row.requested_by, row.items, row.reason) == (None, 0, "late capture: attempt_not_live")
    assert await _state(db_engine, "orders", order_id) == "pending_payment"
    created = (
        "SELECT count(*) FROM audit_logs WHERE action = 'refund.created'"
        " AND entity_id = :r AND actor_user_id IS NULL"
    )
    assert await count(db_engine, created, r=row.id) == 1
    assert await count(db_engine, NOTICES, r=str(row.id)) == 0  # Q7: at settlement only


async def test_the_unique_index_is_the_last_guard_against_a_second_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id, payment_id = await _expired_order(db_engine, db_session)
    await late_capture(db_engine, payment_id, 1000)
    again = NewRefund(
        order_id=order_id,
        payment_id=payment_id,
        provider=PaymentProvider.MOCK,
        kind=RefundKind.LATE_CAPTURE,
        items=(),
        currency="USD",
        reason="late capture: attempt_not_live",
        requested_by=None,
        approved_by=None,
        initiated_at=datetime.now(UTC),
        late_amount_cents=1000,
    )
    async with async_sessionmaker(db_engine)() as session, session.begin():
        assert await SqlRefundStore(session).insert_late_capture(again) is None
    assert len(await late_refunds(db_engine, payment_id)) == 1


async def test_an_overpayment_on_a_live_attempt_is_owed_in_full(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="pending")
    payment_id = await payment_of(db_engine, order.order_id)
    assert await late_capture(db_engine, payment_id, 1500) is Outcome.LATE_CAPTURE_AND_FAIL
    (row,) = await late_refunds(db_engine, payment_id)
    assert (row.amount_cents, row.reason) == (1500, "late capture: amount_mismatch")


@pytest.mark.parametrize(
    ("captured", "currency", "amount", "stored", "notes"),
    [
        (None, "USD", 1000, "USD", (NO_AMOUNT_NOTE,)),
        (90000, "LBP", 90000, "LBP", ()),
        (90000, "lbp", 90000, "LBP", ()),
        (700, "L$", 700, "USD", (BAD_CURRENCY_NOTE,)),
        (None, "LBP", 1000, "USD", (NO_AMOUNT_NOTE,)),  # the attempt's amount, in USD
        (-5, "LBP", 1000, "USD", (NO_AMOUNT_NOTE,)),  # a negative amount is no amount
    ],
    ids=["no-amount", "lbp", "lowercase", "unreadable", "no-amount-lbp", "negative-lbp"],
)
async def test_q6_the_reported_amount_and_currency(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    captured: int | None,
    currency: str,
    amount: int,
    stored: str,
    notes: tuple[str, ...],
) -> None:
    _, payment_id = await _expired_order(db_engine, db_session)
    await late_capture(db_engine, payment_id, captured, currency)
    (row,) = await late_refunds(db_engine, payment_id)
    assert (row.amount_cents, row.currency) == (amount, stored)
    assert row.reason == "; ".join(("late capture: attempt_not_live", *notes))


async def test_a_zero_capture_leaves_no_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    _, payment_id = await _expired_order(db_engine, db_session)
    await late_capture(db_engine, payment_id, 0)
    assert await late_refunds(db_engine, payment_id) == []


async def test_i15_the_admin_fails_reissues_and_settles_it_on_an_unpaid_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id, payment_id = await _expired_order(db_engine, db_session)
    await late_capture(db_engine, payment_id, 1200)
    (row,) = await late_refunds(db_engine, payment_id)
    refund = str(row.id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        failed = ok(act(client, refund, "fail", {"reason": "Card closed."}))
        assert failed["owed"] and refund in queue_ids(client, order_id)
        twin = ok(act(client, refund, "reissue"), 201)
        assert (twin["kind"], twin["amount_cents"], twin["reissue_of_refund_id"]) == (
            "late_capture",
            1200,
            refund,
        )
        assert refund not in queue_ids(client, order_id) and twin["id"] in queue_ids(
            client, order_id
        )
        assert ok(act(client, twin["id"], "settle", {"reference": "dash-9"}))["status"] == (
            "settled"
        )
    assert await count(db_engine, NOTICES, r=twin["id"]) == 1  # Q7: once paid back
    assert await count(db_engine, NOTICES, r=refund) == 0
    assert await _state(db_engine, "orders", order_id) == "pending_payment"
    assert await _state(db_engine, "payments", payment_id) == "expired"


async def test_a_mistaken_late_capture_obligation_can_be_voided(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id, payment_id = await _expired_order(db_engine, db_session)
    await late_capture(db_engine, payment_id, 1000)
    (row,) = await late_refunds(db_engine, payment_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        voided = ok(act(client, row.id, "void", {"reason": "Provider reversed it."}))
        assert voided["status"] == "voided" and str(row.id) not in queue_ids(client, order_id)


async def test_a_late_capture_beside_a_paid_retry_never_touches_its_refunds(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    first = await attempt(db_session, order.order_id, status="expired")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(line, 300)]), 201)
        assert await late_capture(db_engine, first, 1000) is Outcome.LATE_CAPTURE
        assert await statuses(db_engine, order.order_id) == (
            "partially_refunded",
            "partially_refunded",
        )
        (late,) = await late_refunds(db_engine, first)
        ok(act(client, late.id, "settle", {}))
        ok(create(client, order.order_id, [(line, 700)]), 201)  # the paid balance is whole
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
