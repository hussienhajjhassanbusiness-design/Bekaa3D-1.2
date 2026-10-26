"""`release_stale` on Postgres, one test per T2 row (VS-024 plan 3.1, 6.2): only an
explicit `failed` or `expired` for the latest attempt releases; every other answer
writes nothing but its alert. Each test runs the job from its own far-past epoch."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ordering.infrastructure.orders import release_candidates_query
from app.payments.infrastructure import release, verification
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_stale
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    UNTOUCHED,
    YEARS_AHEAD,
    Down,
    SeededOrder,
    Spy,
    admin,
    alerts,
    drop_alert_emails,  # noqa: F401
    explain,
    factory,
    forget_provider_alerts,
    keyset_start,
    one,
    provider_alerts,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import (
    OPEN_TRANSACTIONS,
    Hanging,
    NoStatus,
    _forget,
)
from tests.integration.payments.verification_support import Seeded, mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

LATER = timedelta(hours=1)  # past the 30 min hold, inside the 24 h grace
HISTORY = """
    SELECT actor_user_id, reason FROM order_status_history
    WHERE order_id = :o AND to_status = 'cancelled'
"""


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 6, 1, tzinfo=UTC)


async def _run(
    engine: AsyncEngine, providers: Any, start: datetime, now: datetime
) -> dict[str, int]:
    return await release_stale(factory(engine), providers, now=now, start_after=keyset_start(start))


async def _due(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, **attempt: Any
) -> tuple[SeededOrder, uuid.UUID]:
    order = await seed_order(db, placed_at=at)
    payment_id = await seed_attempt(db, order, initiated_at=at, mock=mock, **attempt)
    return order, payment_id


def _as_seeded(order: SeededOrder, payment_id: uuid.UUID) -> Seeded:
    return Seeded(order.user_id, order.order_id, payment_id, "", "buyer@example.com")


# --- Explicit answers release ------------------------------------------------------------


@pytest.mark.parametrize(("state", "year"), [("failed", 1930), ("expired", 1931)])
async def test_an_explicit_answer_releases_the_order(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    state: str,
    year: int,
) -> None:
    at = epoch(year)
    order, payment_id = await _due(db_session, mock, at, state=state)
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["seen"], counts["released"]) == (1, 1), counts
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == state
    released = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert released.status == "cancelled" and released.cancelled_at is not None
    assert (released.lines, released.lines_stamped) == (["cancelled"], True)
    assert (released.released_audits, released.notices, released.emails) == (1, 1, 1)
    async with db_engine.connect() as conn:
        history = (await conn.execute(text(HISTORY), {"o": order.order_id})).all()
        audit = await conn.scalar(
            text(
                "SELECT after_data FROM audit_logs WHERE entity_id = :o"
                " AND action = 'order.checkout_released'"
            ),
            {"o": order.order_id},
        )
    assert {tuple(row) for row in history} == {(None, "hold_expired")} and len(history) == 2
    assert (audit["source"], audit["reason"], audit["payment_id"]) == (
        "job",
        f"provider_{state}",
        str(payment_id),
    )
    again = await seed_order(
        db_session, placed_at=at, user_id=order.user_id, stl_id=order.stl_id
    )  # the same customer can check out the same STL again
    assert (await one(db_engine, ORDER_STATE, o=again.order_id)).lines == ["pending"]


async def test_an_attempt_failed_by_checkout_is_asked_again_before_release(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Tx2's `failed` is our conclusion, not the provider's: it must still say so."""
    at = epoch(1932)
    order, payment_id = await _due(db_session, mock, at, status="failed")
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["released"], counts["skipped"]) == (0, 1), counts
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"
    await mock.simulate(payment_id, "expired")
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert counts["released"] == 1, counts
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"


# --- Money arrived: applied, never released ------------------------------------------------


async def test_paid_exactly_is_paid_and_not_released(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1933)
    order, payment_id = await _due(db_session, mock, at, state="paid")
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["applied"], counts["released"]) == (1, 0), counts
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "paid"
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines, state.cancelled_at) == (
        "in_progress",
        ["awaiting_delivery"],
        None,
    )


async def test_a_mismatched_capture_is_a_late_capture_and_not_released(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1934)
    await admin(db_session)
    order, payment_id = await _due(db_session, mock, at)
    await mock.simulate(payment_id, "paid", 900)
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["applied"], counts["released"]) == (1, 0), counts
    payment = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert payment.late_captured_at is not None
    assert (payment.status, payment.captured_amount_cents) == ("failed", 900)
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines) == ("pending_payment", ["pending"])
    assert (await alerts(db_engine, payment_id)) == {"late_capture": 1}


# --- No explicit answer: nothing written but the alert ------------------------------------


@pytest.mark.parametrize(
    ("answer", "year", "alert"),
    [
        ("pending", 1935, "stuck"),
        ("processing", 1936, "stuck"),
        ("unknown", 1937, "reference_unknown"),
        ("error", 1938, "provider_unavailable"),
        ("timeout", 1939, "provider_unavailable"),
    ],
)
async def test_no_explicit_answer_never_releases(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    year: int,
    alert: str,
) -> None:
    at = epoch(year)
    order, payment_id = await _due(db_session, mock, at)
    providers: dict[str, Any] = {"mock": mock}
    if answer == "processing":
        await mock.simulate(payment_id, "processing")
    elif answer == "unknown":
        await _forget(_as_seeded(order, payment_id))
    elif answer == "error":
        providers = {"mock": Down()}
    elif answer == "timeout":
        monkeypatch.setattr(verification, "PROVIDER_TIMEOUT_SECONDS", 0.3)
        hanging = Hanging()
        providers = {"mock": hanging}
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    counts = await _run(db_engine, providers, at, at + LATER)
    assert counts["released"] == 0 and counts["seen"] == 1, counts
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before
    assert await alerts(db_engine, payment_id) == {alert: 1}


async def test_an_open_breaker_stops_asking_and_never_releases(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1940)
    await forget_provider_alerts(db_engine)
    seeded = [await _due(db_session, mock, at + timedelta(seconds=i)) for i in range(5)]
    before = [await one(db_engine, UNTOUCHED, o=o.order_id) for o, _ in seeded]
    down = Down()
    counts = await _run(db_engine, {"mock": down}, at, at + LATER)
    assert down.calls == 3, "the breaker opens after PROVIDER_BREAKER_FAILURES"
    assert (counts["deferred"], counts["breaker_open"], counts["released"]) == (5, 2, 0)
    assert [await one(db_engine, UNTOUCHED, o=o.order_id) for o, _ in seeded] == before
    assert await provider_alerts(db_engine) == 1
    for _, payment_id in seeded:
        assert await alerts(db_engine, payment_id) == {"provider_unavailable": 1}


async def test_an_unprocessed_event_skips_the_order_without_asking(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1941)
    order, payment_id = await _due(db_session, mock, at, state="expired")
    await seed_event(db_session, payment_id, received_at=at)
    spy = Spy(mock)
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    counts = await _run(db_engine, {"mock": spy}, at, at + LATER)
    assert (spy.calls, counts["released"], counts["skipped"]) == (0, 0, 1)
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before
    assert await alerts(db_engine, payment_id) == {"event_unverified": 1}


async def test_a_no_status_provider_is_never_released_and_release_due_is_raised_once(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1942)
    order, payment_id = await _due(db_session, mock, at, state="expired")
    stub = NoStatus()
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    for later in (LATER, timedelta(hours=25), timedelta(hours=26), timedelta(days=400)):
        counts = await _run(db_engine, {"mock": stub}, at, at + later)
        assert counts["released"] == 0, counts
    assert stub.calls == []
    assert await one(db_engine, UNTOUCHED, o=order.order_id) == before
    assert await alerts(db_engine, payment_id) == {"release_due": 1}


# --- Shapes, selection and paging ---------------------------------------------------------


async def test_physical_lines_are_cancelled_with_the_stl(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1943)
    order = await seed_order(db_session, placed_at=at, physical=True)
    await seed_attempt(db_session, order, initiated_at=at, mock=mock, state="expired")
    assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["released"] == 1
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines, state.lines_stamped) == (
        "cancelled",
        ["cancelled", "cancelled"],
        True,
    )


async def test_a_cash_order_is_never_selected(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """VS-028's belt: even a cash row seeded `pending_payment` is not a candidate."""
    at = epoch(1944)
    cash = await seed_order(
        db_session,
        placed_at=at,
        physical=True,
        stl=False,
        payment_method="cash",
        cash_terms_accepted_at=at,
        digital_terms_accepted_at=None,
        digital_terms_version=None,
    )
    before = await one(db_engine, UNTOUCHED, o=cash.order_id)
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert counts["seen"] == 0, counts
    assert await one(db_engine, UNTOUCHED, o=cash.order_id) == before


async def test_an_order_behind_120_skipped_orders_is_released_in_the_same_run(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Keyset paging: 120 orders whose newest attempt is not yet due come first."""
    at = epoch(1945)
    now = at + timedelta(days=1)
    holder = await seed_order(db_session, placed_at=at - timedelta(days=1), with_lines=False)
    await db_session.execute(
        text(
            """
            WITH o AS (
              INSERT INTO orders (id, order_number, user_id, customer_email_snapshot, source,
                status, payment_method, subtotal_cents, total_cents, terms_accepted_at,
                placed_at)
              SELECT gen_random_uuid(), 'B3D-P' || lpad(g::text, 3, '0') || :tag, :u,
                'buyer@example.com', 'cart', 'pending_payment', 'online', 1000, 1000,
                CAST(:at AS timestamptz), CAST(:at AS timestamptz) + g * interval '1 second'
              FROM generate_series(1, 120) g RETURNING id)
            INSERT INTO payments (order_id, provider, order_payment_method, status,
              amount_cents, initiated_at)
            SELECT id, 'mock', 'online', 'pending', 1000, :recent FROM o
            """
        ),
        {
            "u": holder.user_id,
            "at": at,
            "recent": now - timedelta(minutes=1),
            "tag": uuid.uuid4().hex[:4].upper(),
        },
    )
    await db_session.commit()
    last = await seed_order(db_session, placed_at=at + timedelta(minutes=10))
    await seed_attempt(db_session, last, initiated_at=at, mock=mock, state="expired")
    counts = await _run(db_engine, {"mock": mock}, at, now)
    assert (counts["seen"], counts["not_due"], counts["released"]) == (121, 120, 1), counts
    assert (await one(db_engine, ORDER_STATE, o=last.order_id)).status == "cancelled"


async def test_the_release_selection_uses_ix_orders_status_placed(
    db_engine: AsyncEngine,
) -> None:
    query = release_candidates_query(
        placed_before=epoch(1946), after=keyset_start(epoch(1946)), limit=50
    )
    natural = await explain(db_engine, query, seqscan=True)
    forced = await explain(db_engine, query, seqscan=False)
    print(f"\nEXPLAIN release candidates (planner's choice):\n{natural}")
    print(f"EXPLAIN release candidates (enable_seqscan = off):\n{forced}")
    assert "ix_orders_status_placed" in forced, forced
    assert "LockRows" not in natural + forced


async def test_no_transaction_is_open_while_the_release_job_asks(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = epoch(1947)
    order, _ = await _due(db_session, mock, at)
    hanging = Hanging()
    task = asyncio.create_task(_run(db_engine, {"mock": hanging}, at, at + LATER))
    await asyncio.wait_for(hanging.entered.wait(), 5)
    async with db_engine.connect() as conn:
        open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
    hanging.release.set()
    counts = await asyncio.wait_for(task, 10)
    assert open_during_call == 0
    assert (counts["seen"], counts["released"]) == (1, 0)
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"


async def test_one_run_over_a_seeded_set_counts_each_outcome(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1948)
    step = iter(range(1, 100))

    async def due(**attempt: Any) -> uuid.UUID:
        placed = at + timedelta(seconds=next(step))
        order = await seed_order(db_session, placed_at=placed)
        return await seed_attempt(db_session, order, initiated_at=placed, mock=mock, **attempt)

    await due(state="expired")
    await due(state="failed")
    await due(state="paid")
    mismatch = await due()
    await mock.simulate(mismatch, "paid", 900)
    await due()  # pending
    with_event = await due(state="expired")
    await seed_event(db_session, with_event, received_at=at)
    not_due = await seed_order(db_session, placed_at=at + timedelta(seconds=50))
    await seed_attempt(db_session, not_due, initiated_at=at + LATER, mock=mock)
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    print("\nRELEASE RUN COUNTERS:", counts)
    assert counts == {
        "seen": 7,
        "released": 2,
        "applied": 2,
        "not_due": 1,
        "skipped": 2,
        "deferred": 0,
        "breaker_open": 0,
        "rechecked": 0,
        "truncated": 0,
    }


async def test_only_the_latest_attempt_is_asked(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """An older attempt's `expired` never releases the order its newer attempt still holds."""
    at = epoch(1949)
    order = await seed_order(db_session, placed_at=at)
    await seed_attempt(
        db_session, order, initiated_at=at, mock=mock, status="failed", state="expired"
    )
    latest = await seed_attempt(
        db_session, order, initiated_at=at + timedelta(minutes=1), mock=mock
    )
    spy = Spy(mock)
    counts = await _run(db_engine, {"mock": spy}, at, at + 2 * LATER)
    assert (spy.calls, counts["released"]) == (1, 0), counts
    assert await alerts(db_engine, latest) == {"stuck": 1}  # the newest attempt was asked
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"


async def test_the_release_tx_b_locks_orders_lines_then_payments(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = epoch(1929)
    await _due(db_session, mock, at, state="expired")
    with captured(db_engine.sync_engine) as statements:
        assert (await _run(db_engine, {"mock": mock}, at, at + LATER))["released"] == 1
    first_lock = next(i for i, s in enumerate(statements) if "FOR UPDATE" in s)
    selection_and_tx_a = statements[:first_lock]
    tx_b = statements[first_lock:]
    print("\nRELEASE before Tx B:", *(s[:110] for s in selection_and_tx_a), sep="\n  ")
    print("RELEASE Tx B:", *(s[:110] for s in tx_b), sep="\n  ")
    assert not any("FOR UPDATE" in s for s in selection_and_tx_a)
    assert tx_b[0].startswith("SELECT orders.id") and tx_b[0].endswith("FOR UPDATE")
    assert tx_b[1].endswith("ORDER BY order_items.id FOR UPDATE")
    assert tx_b[2].startswith("SELECT payments.id") and tx_b[2].endswith(
        "ORDER BY payments.id FOR UPDATE"
    )
    assert tx_b[3].startswith("SELECT count(*)") and "FOR UPDATE" not in tx_b[3]
    writes = [
        s.split()[0] + " " + s.split()[2 if s.startswith("INSERT") else 1]
        for s in tx_b
        if s.startswith(("UPDATE", "INSERT"))
    ]
    print("  writes:", writes)
    assert writes == [
        "UPDATE payments",  # apply_result: the explicit `expired`
        "INSERT audit_logs",  # payment.expired
        "UPDATE orders",  # cancelled_at
        "UPDATE order_items",  # pending -> cancelled
        "INSERT order_status_history",
        "UPDATE orders",  # status
        "INSERT order_status_history",
        "INSERT audit_logs",  # order.checkout_released
        "INSERT email_outbox",
        "INSERT notifications",
    ]
    tables = {s.split(" FROM ")[1].split()[0] for s in tx_b if s.endswith("FOR UPDATE")}
    # VS-036 (ADR-044, plan 8.1): release_unpaid_order's badge hook adds the buyer's reviews
    # FOR UPDATE (rank 9, after R_user at 7), after payments (rank 4).
    assert tables == {"orders", "order_items", "payments", "reviews"}


async def test_an_event_that_arrives_during_the_question_stops_the_release(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The re-check under the locks: an event stored between Tx A and Tx B wins."""
    at = epoch(1928)
    order, payment_id = await _due(db_session, mock, at, state="expired")
    real = getattr(release, "ask_provider")  # noqa: B009

    async def ask_while_an_event_lands(providers: Any, payment: Any) -> Any:
        answer = await real(providers, payment)
        await seed_event(db_session, payment_id, received_at=at)
        return answer

    monkeypatch.setattr(release, "ask_provider", ask_while_an_event_lands)
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["released"], counts["rechecked"]) == (0, 1), counts
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.lines) == ("pending_payment", ["pending"])


async def test_an_older_live_attempt_blocks_the_release(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Seeded only (retry cannot make it): the order is never cancelled under a live attempt."""
    at = epoch(1927)
    order = await seed_order(db_session, placed_at=at)
    live = await seed_attempt(db_session, order, initiated_at=at, mock=mock)
    await seed_attempt(
        db_session,
        order,
        initiated_at=at + timedelta(minutes=1),
        mock=mock,
        status="failed",
        state="expired",
    )
    counts = await _run(db_engine, {"mock": mock}, at, at + LATER)
    assert (counts["released"], counts["rechecked"]) == (0, 1), counts
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"
    assert (await one(db_engine, PAYMENT_STATE, p=live)).status == "pending"
