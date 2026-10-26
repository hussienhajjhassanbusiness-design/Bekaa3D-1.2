"""Manual release (VS-024 plan 2.5) and manual confirm (2.3) at the service level on
Postgres; the routes, CSRF, MFA and rate limits are step 12. Each refusal writes nothing:
the caller's unit of work rolls back, as the request's would."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.alerts import AlertKind
from app.payments.domain.exceptions import (
    ManualConfirmRefusedError,
    ManualReleaseRefusedError,
    OrderNotFoundError,
    PaymentReferenceMismatchError,
)
from app.payments.domain.manual import ConfirmRefusal
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure.alerts import SqlPaymentAlerts
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_order_by_admin
from app.payments.infrastructure.verification import apply_provider_result
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    PAYMENT_STATE,
    UNTOUCHED,
    YEARS_AHEAD,
    SeededOrder,
    drop_alert_emails,  # noqa: F401
    one,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import NoStatus
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

GRACE = timedelta(hours=24)
REASON = "dashboard shows no payment; customer confirmed abandonment by phone"
NO_STATUS = {"mock": NoStatus()}


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 3, 1, tzinfo=UTC)


async def _admin(db: AsyncSession) -> uuid.UUID:
    return (await create_user(db, role=UserRole.ADMIN)).id


async def _release(
    engine: AsyncEngine, order_id: uuid.UUID, admin_id: uuid.UUID, now: datetime, **kw: Any
) -> Any:
    async with async_sessionmaker(engine)() as session, session.begin():
        return await release_order_by_admin(
            session,
            order_id,
            admin_id=admin_id,
            reason=REASON,
            events_reviewed=kw.pop("events_reviewed", False),
            hold=HOLD,
            now=now,
            **kw,
        )


async def _confirm(
    engine: AsyncEngine, payment_id: uuid.UUID, admin_id: uuid.UUID, **kw: Any
) -> Outcome:
    async with async_sessionmaker(engine)() as session, session.begin():
        return await confirm_payment_manually(
            session,
            kw.pop("providers", NO_STATUS),
            payment_id,
            admin_id=admin_id,
            provider_reference=kw.pop("provider_reference", f"dash_{payment_id.hex}"),
            amount_cents=kw.pop("amount_cents", 1000),
            currency=kw.pop("currency", "USD"),
            reason="dashboard shows a capture of 10.00 USD",
            **kw,
        )


async def _due(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, **attempt: Any
) -> tuple[SeededOrder, uuid.UUID]:
    order = await seed_order(db, placed_at=at)
    return order, await seed_attempt(db, order, initiated_at=at, mock=mock, **attempt)


# --- Manual release -------------------------------------------------------------------------


async def test_a_release_before_the_grace_is_refused_and_writes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1900)
    admin_id = await _admin(db_session)
    order, _ = await _due(db_session, mock, at)
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    with pytest.raises(ManualReleaseRefusedError) as refused:
        await _release(
            db_engine, order.order_id, admin_id, at + HOLD + GRACE - timedelta(seconds=1)
        )
    assert refused.value.reason == "grace_not_elapsed"
    assert refused.value.available_at == at + HOLD + GRACE
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before


@pytest.mark.parametrize(
    ("reference", "unknown", "year", "early"),
    [(False, True, 1901, True), (True, True, 1902, False), (False, False, 1899, False)],
    ids=["no-reference-unknown", "reference-unknown", "no-reference-never-asked"],
)
async def test_the_early_release_needs_no_reference_and_an_unknown_answer(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    reference: bool,
    unknown: bool,
    year: int,
    early: bool,
) -> None:
    """Revision 2, Q7: early only for the checkout crash window the provider never saw."""
    at = epoch(year)
    admin_id = await _admin(db_session)
    order, payment_id = await _due(db_session, mock, at, reference=reference)
    if unknown:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await SqlPaymentAlerts(session).raise_alert(
                AlertKind.REFERENCE_UNKNOWN,
                payment_id=payment_id,
                order_id=order.order_id,
                details={},
                dedupe_window=None,
            )
    now = at + HOLD
    if early:
        assert (await _release(db_engine, order.order_id, admin_id, now)).order_id == order.order_id
        assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"
    else:
        with pytest.raises(ManualReleaseRefusedError, match="grace_not_elapsed"):
            await _release(db_engine, order.order_id, admin_id, now)


async def test_a_release_after_the_grace_cancels_with_the_admin_on_every_row(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1903)
    admin_id = await _admin(db_session)
    order, payment_id = await _due(db_session, mock, at)
    released = await _release(
        db_engine,
        order.order_id,
        admin_id,
        at + HOLD + GRACE,
        request_id="req-1903",
        ip_hash="iphash-1903",
    )
    assert released.attempts_expired == (payment_id,) and released.events_dismissed == ()
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines, state.lines_stamped) == ("cancelled", ["cancelled"], True)
    assert (state.released_audits, state.notices, state.emails) == (1, 1, 1)
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "expired"
    async with db_engine.connect() as conn:
        history = (
            await conn.execute(
                text(
                    "SELECT DISTINCT actor_user_id, reason FROM order_status_history"
                    " WHERE order_id = :o AND to_status = 'cancelled'"
                ),
                {"o": order.order_id},
            )
        ).all()
        expired = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, after_data->>'source' AS source FROM audit_logs"
                    " WHERE entity_id = :p AND action = 'payment.expired'"
                ),
                {"p": payment_id},
            )
        ).one()
        audit = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, request_id, ip_hash, after_data FROM audit_logs"
                    " WHERE entity_id = :o AND action = 'order.checkout_released'"
                ),
                {"o": order.order_id},
            )
        ).one()
    assert [tuple(row) for row in history] == [(admin_id, "released_by_admin")]
    assert tuple(expired) == (admin_id, "admin_release")
    assert (audit.actor_user_id, audit.request_id, audit.ip_hash) == (
        admin_id,
        "req-1903",
        "iphash-1903",
    )
    assert audit.after_data["reason"] == REASON
    assert audit.after_data["attempts_expired"] == [str(payment_id)]
    assert audit.after_data["source"] == "admin"


async def test_unprocessed_events_need_review_and_are_then_dismissed(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1904)
    admin_id = await _admin(db_session)
    order, payment_id = await _due(db_session, mock, at)
    events = sorted(
        [await seed_event(db_session, payment_id, received_at=at) for _ in range(2)], key=str
    )
    now = at + HOLD + GRACE
    with pytest.raises(ManualReleaseRefusedError) as refused:
        await _release(db_engine, order.order_id, admin_id, now)
    assert (refused.value.reason, refused.value.unprocessed_events) == ("unprocessed_events", 2)
    released = await _release(db_engine, order.order_id, admin_id, now, events_reviewed=True)
    assert list(released.events_dismissed) == events
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT processed_at IS NOT NULL AS done, processing_error FROM webhook_events"
                    " WHERE payment_id = :p"
                ),
                {"p": payment_id},
            )
        ).all()
        listed = await conn.scalar(
            text(
                "SELECT after_data->'events_dismissed' FROM audit_logs WHERE entity_id = :o"
                " AND action = 'order.checkout_released'"
            ),
            {"o": order.order_id},
        )
    assert {tuple(row) for row in rows} == {(True, "dismissed_by_admin")}
    assert listed == [str(e) for e in events]


@pytest.mark.parametrize(
    ("shape", "year", "reason"),
    [
        ("paid", 1905, "order_not_payable"),
        ("released", 1906, "order_cancelled"),
        ("cash", 1907, "cash_order"),
    ],
)
async def test_a_release_is_refused_for_paid_released_and_cash_orders(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    shape: str,
    year: int,
    reason: str,
) -> None:
    at = epoch(year)
    admin_id = await _admin(db_session)
    if shape == "cash":
        order = await seed_order(
            db_session,
            placed_at=at,
            physical=True,
            stl=False,
            payment_method="cash",
            cash_terms_accepted_at=at,
            digital_terms_accepted_at=None,
            digital_terms_version=None,
            status="in_progress",
        )
    else:
        order, payment_id = await _due(db_session, mock, at, state="paid")
        async with async_sessionmaker(db_engine)() as session, session.begin():
            answer = (
                ProviderResult("paid", 1000, "USD")
                if shape == "paid"
                else ProviderResult("expired", None, None)
            )
            await apply_provider_result(
                session, payment_id, answer, source="reconcile", actor_user_id=None
            )
        if shape == "released":
            await _release(db_engine, order.order_id, admin_id, at + HOLD + GRACE)
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    with pytest.raises(ManualReleaseRefusedError, match=reason):
        await _release(db_engine, order.order_id, admin_id, at + HOLD + GRACE)
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before


async def test_an_unknown_order_is_not_found(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    with pytest.raises(OrderNotFoundError):
        await _release(db_engine, uuid.uuid4(), await _admin(db_session), epoch(1908))


async def test_a_manual_release_locks_orders_lines_then_payments(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1909)
    admin_id = await _admin(db_session)
    order, _ = await _due(db_session, mock, at)
    with captured(db_engine.sync_engine) as statements:
        await _release(db_engine, order.order_id, admin_id, at + HOLD + GRACE)
    locks = [s for s in statements if "FOR UPDATE" in s]
    print("\nMANUAL RELEASE:", *(s[:110] for s in statements[:6]), sep="\n  ")
    assert statements[0].startswith("SELECT orders.id") and statements[0].endswith("FOR UPDATE")
    assert statements[1].endswith("ORDER BY order_items.id FOR UPDATE")
    assert statements[2].endswith("ORDER BY payments.id FOR UPDATE")
    assert statements[3].startswith("SELECT count(*)") and "webhook_events" in statements[3]
    # VS-036 (ADR-044, plan 8.1): release_unpaid_order's badge hook adds R_user (rank 7) and
    # the buyer's reviews FOR UPDATE (rank 9), after payments (rank 4).
    assert len(locks) == 4, locks
    assert "FROM reviews" in locks[3]


# --- Manual confirm ---------------------------------------------------------------------------

CONFIRM_ROWS = """
    SELECT
      (SELECT count(*) FROM audit_logs WHERE entity_id = :p) AS audits,
      (SELECT count(*) FROM email_outbox WHERE payload->>'order_id' = CAST(:o AS text)) AS emails,
      (SELECT count(*) FROM notifications WHERE payload->>'order_id' = CAST(:o AS text))
        AS notices,
      (SELECT count(*) FROM webhook_events WHERE payment_id = :p AND processed_at IS NULL)
        AS unprocessed
"""


async def test_a_status_provider_is_never_confirmed_by_hand(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    order, payment_id = await _due(db_session, mock, epoch(1890))
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    with pytest.raises(ManualConfirmRefusedError) as refused:
        await _confirm(db_engine, payment_id, await _admin(db_session), providers={"mock": mock})
    assert refused.value.refusal is ConfirmRefusal.STATUS_QUERY_AVAILABLE
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before


@pytest.mark.parametrize(
    ("amount", "currency"),
    [(999, "USD"), (1001, "USD"), (0, "USD"), (1000, "EUR")],
    ids=["minus-1", "plus-1", "zero", "eur"],
)
async def test_a_differing_amount_writes_nothing_and_the_right_one_then_pays(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    amount: int,
    currency: str,
) -> None:
    admin_id = await _admin(db_session)
    order, payment_id = await _due(db_session, mock, epoch(1891), reference=False)
    await seed_event(db_session, payment_id, received_at=epoch(1891))
    before = (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, CONFIRM_ROWS, p=payment_id, o=str(order.order_id)),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
    )
    with pytest.raises(ManualConfirmRefusedError) as refused:
        await _confirm(db_engine, payment_id, admin_id, amount_cents=amount, currency=currency)
    assert refused.value.refusal is ConfirmRefusal.AMOUNT_MISMATCH
    assert refused.value.expected_amount_cents == 1000
    assert (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, CONFIRM_ROWS, p=payment_id, o=str(order.order_id)),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
    ) == before
    assert await _confirm(db_engine, payment_id, admin_id) is Outcome.APPLY_PAID


async def test_an_exact_confirm_pays_closes_events_and_audits_the_admin(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    admin_id = await _admin(db_session)
    order, payment_id = await _due(db_session, mock, epoch(1892), reference=False)
    await seed_event(db_session, payment_id, received_at=epoch(1892))
    assert await _confirm(db_engine, payment_id, admin_id, request_id="r", ip_hash="h") is (
        Outcome.APPLY_PAID
    )
    assert await _confirm(db_engine, payment_id, admin_id) is Outcome.NOOP  # double submit
    payment = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert (payment.status, payment.provider_payment_id, payment.captured_amount_cents) == (
        "paid",
        f"dash_{payment_id.hex}",
        1000,
    )
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines) == ("in_progress", ["awaiting_delivery"])
    rows = await one(db_engine, CONFIRM_ROWS, p=payment_id, o=str(order.order_id))
    assert (rows.unprocessed, rows.emails, rows.notices) == (0, 1, 1)
    async with db_engine.connect() as conn:
        audits = (
            await conn.execute(
                text(
                    "SELECT action, actor_user_id, request_id, after_data FROM audit_logs"
                    " WHERE entity_id = :p ORDER BY created_at"
                ),
                {"p": payment_id},
            )
        ).all()
    assert [(a.action, a.actor_user_id) for a in audits] == [
        ("payment.verified", admin_id),
        ("payment.manual_confirmation", admin_id),
        ("payment.manual_confirmation", admin_id),
    ]
    first = audits[1].after_data
    assert (first["outcome"], first["typed_amount_cents"], first["events_marked_processed"]) == (
        "apply_paid",
        1000,
        1,
    )
    assert (first["provider_reference"], first["attempt_status_before"]) == (
        f"dash_{payment_id.hex}",
        "pending",
    )
    assert audits[1].request_id == "r"


async def test_a_reference_that_differs_or_belongs_to_another_payment_is_refused(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    admin_id = await _admin(db_session)
    _, stored = await _due(db_session, mock, epoch(1893))  # has the mock's reference
    with pytest.raises(PaymentReferenceMismatchError):
        await _confirm(db_engine, stored, admin_id, provider_reference="dash_other")
    stored_ref = (await one(db_engine, PAYMENT_STATE, p=stored)).provider_payment_id
    _, other = await _due(db_session, mock, epoch(1893), reference=False)
    with pytest.raises(PaymentReferenceMismatchError):
        await _confirm(db_engine, other, admin_id, provider_reference=stored_ref)
    assert (await one(db_engine, PAYMENT_STATE, p=other)).status == "pending"


async def test_a_confirm_takes_the_same_locks_as_the_webhook(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    admin_id = await _admin(db_session)
    _, payment_id = await _due(db_session, mock, epoch(1894), reference=False)
    with captured(db_engine.sync_engine) as statements:
        await _confirm(db_engine, payment_id, admin_id)
    order = [s.split(" FROM ")[1].split()[0] for s in statements if s.endswith("FOR UPDATE")]
    print("\nCONFIRM FOR UPDATE:", order)
    assert statements[0].startswith("SELECT payments.id") and "FOR UPDATE" not in statements[0]
    # The confirm's own locks, then apply_result's on the rows it already holds, then the
    # paid STL's live offers (ADR-037).
    # VS-036 (ADR-044, plan 8.1): mark_order_paid's badge hook locks the buyer's reviews
    # (rank 9, after R_user at 7) between the payments (rank 4) and the offers (rank 10).
    assert order == ["orders", "order_items", "payments"] * 2 + ["reviews", "offers"]
