"""VS-043 revenue over HTTP on real Postgres (plan 6.2 R1-R12, R15; api-endpoints 27.1). Each
scenario runs through the real money paths and asserts exact cents on its own Beirut day."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, mfa_admin
from tests.integration.fulfillment.cancel_support import admin_cancel
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import (
    act,
    attempt,
    chargeback,
    create,
    late_capture,
    late_refunds,
    line_state,
    ok,
    paid_cash,
    paid_online,
    payment_of,
    refund_rows,
)
from tests.integration.reporting.support import (
    BEIRUT,
    beirut_noon,
    body,
    free_day,
    net,
    paid_at,
    report,
    revenue,
    stream,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _admin_client() -> TestClient:
    return client_for(main_app)


async def test_r1_r15_a_mixed_order_splits_by_stream_and_equals_its_lines(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session)  # physical 1000 + STL 500, paid in full
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    total = await db_session.scalar(
        text("SELECT total_cents FROM orders WHERE id = :o"), {"o": order.order_id}
    )
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        found = revenue(client, day)
    assert stream(found, "gross") == (1000, 500)
    assert net(found) == (1000, 500, 1500) == (1000, 500, total)
    assert (found["totals"]["paid_lines"], found["totals"]["paid_orders"]) == (2, 1)
    assert found["currency"] == "USD"
    assert found["timezone"] == "Asia/Beirut"
    assert found["unattributed_chargeback_excess_cents"] == 0


async def test_r2_a_partial_refund_reduces_its_stream_pending_and_settled(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 250)]), 201)["id"]
        assert net(revenue(client, day)) == (750, 500, 1250)
        ok(act(client, refund, "settle", {}))
        found = revenue(client, day)
    assert net(found) == (750, 500, 1250)
    assert stream(found, "refunded") == (250, 0)


async def test_r3_unpaid_cash_adds_nothing_and_the_handover_counts_on_its_beirut_day(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    unpaid = await seed_physical_order(db_session, payment_method="cash", line_states=("pending",))
    order = await paid_cash(db_session)
    late_evening = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=22, minutes=30)
    await paid_at(db_engine, order.order_id, late_evening)
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        assert net(revenue(client, day)) == (0, 0, 0)
        next_day = revenue(client, day + timedelta(days=1))
        both = revenue(client, day, day + timedelta(days=1))
    assert net(next_day) == (1000, 0, 1000)
    assert [b["net"]["total_cents"] for b in both["buckets"]] == [0, 1000]
    assert unpaid.order_id != order.order_id


async def test_r4_a_refused_line_of_a_partly_accepted_cash_order_adds_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_cash(db_session, lines=("delivered", "cancelled"))
    await db_session.execute(
        text("UPDATE order_items SET cancel_reason = 'refused' WHERE id = :i"),
        {"i": order.physical[1]},
    )
    await db_session.commit()
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        found = revenue(client, day)
    assert stream(found, "gross") == (1000, 0)
    assert net(found) == (1000, 0, 1000)
    assert found["totals"]["paid_lines"] == 1


async def test_r5_a_partial_amount_refund_then_the_rest_removes_the_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl="delivered")
    assert order.stl is not None
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 200)]), 201)
        assert net(revenue(client, day)) == (1000, 300, 1300)
        assert [i["net_cents"] for i in _sales(client, day)] == [300]
        ok(create(client, order.order_id, [(order.stl, 300)]), 201)
        found = revenue(client, day)
        sales = _sales(client, day)
    assert await line_state(db_engine, order.stl) == "refunded"
    assert net(found) == (1000, 0, 1000)
    assert sales == []


def _sales(client: TestClient, day: object) -> list[dict[str, object]]:
    found = body(report(client, "stl-sales", from_=day, to=day))
    items: list[dict[str, object]] = found["items"]
    return items


async def test_r6_a_failed_refund_reduces_nothing_until_reissued(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 200)]), 201)["id"]
        ok(act(client, refund, "fail", {"reason": "Card closed."}))
        assert net(revenue(client, day)) == (1000, 0, 1000)
        reissue = ok(act(client, refund, "reissue", {}), 201)["id"]
        assert net(revenue(client, day)) == (800, 0, 800)
        ok(act(client, reissue, "settle", {}))
        assert net(revenue(client, day)) == (800, 0, 800)


async def test_r7_a_voided_refund_reduces_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 200)]), 201)["id"]
        ok(act(client, refund, "void", {"reason": "Created by mistake."}))
        assert net(revenue(client, day)) == (1000, 0, 1000)


async def test_r8_a_late_capture_never_appears_and_the_paid_retry_counts_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session)
    failed = await attempt(db_session, order.order_id, status="failed", amount=1500)
    await late_capture(db_engine, failed, 1500)
    assert [r.status for r in await late_refunds(db_engine, failed)] == ["pending"]
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        found = revenue(client, day)
    assert net(found) == (1000, 500, 1500)
    assert stream(found, "refunded") == (0, 0)
    assert found["totals"]["paid_orders"] == 1


async def test_r9_a_chargeback_is_counted_once_on_the_line_it_cancelled(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-045 d2. The chargeback cancels the unfinished line (ADR-042 d17); the line stays a
    paid line and its chargeback item nets it to 0: gross 1000, refunded 1000, net 0."""
    day = await free_day(db_engine)
    order = await paid_online(db_session, physical=("in_production",), stl="delivered")
    line = order.physical[0]
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    payment = await payment_of(db_engine, order.order_id)
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        ok(chargeback(client, order.order_id, payment, 1000, [(line, 1000)]), 201)
        found = revenue(client, day)
    assert await line_state(db_engine, line) == "cancelled"
    assert stream(found, "gross") == (1000, 500)
    assert stream(found, "refunded") == (1000, 0)
    assert net(found) == (0, 500, 500)  # paid 1500 - charged 1000, once
    assert found["totals"]["paid_lines"] == 2


async def test_r9b_a_partial_chargeback_then_a_cancel_nets_the_remainder_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, physical=("in_production",), stl="delivered")
    line = order.physical[0]
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    payment = await payment_of(db_engine, order.order_id)
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        ok(chargeback(client, order.order_id, payment, 600, [(line, 600)]), 201)
        assert net(revenue(client, day)) == (400, 500, 900)
        ok(admin_cancel(client, order.order_id))
        assert await line_state(db_engine, line) == "cancelled"
        assert net(revenue(client, day)) == (0, 500, 500)
        [cancellation] = [
            r for r in await refund_rows(db_engine, order.order_id) if r.kind == "cancellation"
        ]
        assert cancellation.amount_cents == 400
        ok(act(client, cancellation.id, "fail", {"reason": "Card closed."}))
        found = revenue(client, day)
    assert net(found) == (400, 500, 900)  # the 400 is still held: an owed refund
    assert found["totals"]["paid_lines"] == 2


async def test_r9c_a_chargeback_after_a_full_refund_is_excess_not_negative(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    payment = await payment_of(db_engine, order.order_id)
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 1000)]), 201)["id"]
        ok(act(client, refund, "settle", {}))
        ok(chargeback(client, order.order_id, payment, 1000), 201)
        found = revenue(client, day)
    assert net(found) == (0, 0, 0)
    assert found["unattributed_chargeback_excess_cents"] == 1000


async def test_r10_a_chargeback_absorbing_a_pending_refund_subtracts_it_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    payment = await payment_of(db_engine, order.order_id)
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(line, 200)]), 201)
        ok(chargeback(client, order.order_id, payment, 1000, [(line, 800)]), 201)
        found = revenue(client, day)
    assert [r.status for r in await refund_rows(db_engine, order.order_id)] == ["voided"]
    assert net(found) == (0, 0, 0)
    assert stream(found, "refunded") == (1000, 0)


async def test_r11_a_later_refund_lowers_the_day_the_money_came_in(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        before = revenue(client, day, day + timedelta(days=1), group_by="day")
        ok(create(client, order.order_id, [(order.physical[0], 250)]), 201)
        after = revenue(client, day, day + timedelta(days=1), group_by="day")
    assert [b["net"]["total_cents"] for b in before["buckets"]] == [1000, 0]
    assert [b["net"]["total_cents"] for b in after["buckets"]] == [750, 0]
    created = await db_session.scalar(
        text("SELECT created_at FROM refunds WHERE order_id = :o"), {"o": order.order_id}
    )
    assert created.date() > day  # dated by the payment, not by the refund


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"from_": "2026-10-02", "to": "2026-10-01"}, "to"),
        ({"from_": "2025-01-01", "to": "2026-01-02"}, "to"),
        ({"from_": "2019-12-31", "to": "2020-01-02"}, "from"),
        ({"from_": "2100-12-01", "to": "2101-01-01"}, "to"),
    ],
)
async def test_r12_an_out_of_range_period_is_400_invalid_date_range(
    db_session: AsyncSession, params: dict[str, str], field: str
) -> None:
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        for path in ("revenue", "overview", "customers", "stl-sales"):
            problem = body(report(client, path, **params), 400)
            assert problem["code"] == "INVALID_DATE_RANGE"
            assert problem["errors"][0]["loc"] == ["query", field]


async def test_r12_366_days_pass_unparseable_is_422_and_the_default_is_30_days(
    db_session: AsyncSession,
) -> None:
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        assert len(revenue(client, "2024-01-01", "2024-12-31")["buckets"]) == 366
        assert report(client, "revenue", from_="garbage").status_code == 422
        assert report(client, "revenue", group_by="year").status_code == 422
        found = body(report(client, "revenue"))
    today = datetime.now(UTC).astimezone(BEIRUT).date()
    assert (found["from"], found["to"]) == (str(today - timedelta(days=29)), str(today))
    assert len(found["buckets"]) == 30


async def test_week_and_month_buckets(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session, stl=None)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        weekly = revenue(client, day, day + timedelta(days=13), group_by="week")
        monthly = revenue(client, day, day, group_by="month")
    assert weekly["buckets"][0]["start"] == str(day)
    assert sum(b["net"]["total_cents"] for b in weekly["buckets"]) == 1000
    assert monthly["buckets"] == [
        {"start": str(day), "net": {"physical_cents": 1000, "stl_cents": 0, "total_cents": 1000}}
    ]


async def test_an_unknown_order_id_is_never_a_paid_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """A pending (unpaid) online order on the day adds nothing."""
    day = await free_day(db_engine)
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="pending", line_states=("pending",)
    )
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE payments SET initiated_at = :m WHERE order_id = :o"),
            {"m": beirut_noon(day), "o": order.order_id},
        )
    with _admin_client() as client:
        await mfa_admin(client, db_session)
        assert net(revenue(client, day)) == (0, 0, 0)
    assert isinstance(order.order_id, uuid.UUID)
