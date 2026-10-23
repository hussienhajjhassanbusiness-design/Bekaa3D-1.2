"""VS-029 over HTTP: `POST /api/v1/admin/orders/{id}/cash-handover` (SRS 9.8.3; BR-054,
BR-055, BR-143; ADR-024 d4, d9; ADR-040)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.order_support import (
    effects,
    emails,
    hand_over,
    handover_path,
    notifications,
    seed_physical_order,
    states,
)
from tests.integration.ordering.physical_support import usd

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

READY = {"delivery": "shipped", "pickup": "ready_for_pickup"}
DONE = {"delivery": "delivered", "pickup": "picked_up"}


async def _cash_rows(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT status, amount_cents, currency, recorded_by, verified_at,"
                " order_payment_method FROM payments WHERE order_id = :o"
            ),
            {"o": order_id},
        )
        return list(rows.all())


async def _handover_audits(engine: AsyncEngine, order_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT actor_user_id, after_data FROM audit_logs"
                " WHERE action = 'order.cash_handover' AND entity_id = :o"
            ),
            {"o": order_id},
        )
        return list(rows.all())


@pytest.mark.parametrize("fulfillment", ["delivery", "pickup"])
async def test_the_handover_completes_the_order_with_one_paid_cash_payment(
    fulfillment: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    ready = READY[fulfillment]
    order = await seed_physical_order(
        db_session, fulfillment=fulfillment, line_states=[ready, ready], line_totals=[1200, 800]
    )
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        response = hand_over(client, order, 2000)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed" and body["completed_at"] is not None
    assert body["payment_due"] is False and body["amount_due"] is None
    assert [line["fulfillment_status"] for line in body["lines"]] == [DONE[fulfillment]] * 2
    assert all(line["available_actions"] == [] for line in body["lines"])
    [payment] = body["payments"]
    assert (payment["provider"], payment["status"], payment["amount"]) == (
        "cash",
        "paid",
        usd(2000),
    )
    assert payment["recorded_by"] == str(admin.id)
    [row] = await _cash_rows(db_engine, order.order_id)
    assert (row.status, row.amount_cents, row.currency, row.recorded_by) == (
        "paid",
        2000,
        "USD",
        admin.id,
    )
    assert row.verified_at is not None and row.order_payment_method == "cash"
    assert await states(db_engine, order.order_id) == ("completed", [DONE[fulfillment]] * 2)
    [audit] = await _handover_audits(db_engine, order.order_id)
    assert audit.actor_user_id == admin.id
    assert audit.after_data["amount_cents"] == 2000
    assert audit.after_data["payment_id"] == payment["id"]
    [(template, payload)] = await emails(db_engine, order.order_id)
    assert template == f"order_{DONE[fulfillment]}"
    assert payload["cash_receipt"]["amount_cents"] == 2000
    assert payload["cash_receipt"]["payment_id"] == payment["id"]
    assert payload["receipt_actions"] is True
    assert (payload["delivery_fee_note"] is not None) is (fulfillment == "delivery")
    assert await notifications(db_engine, order.order_id) == [f"order.{DONE[fulfillment]}"]


async def test_the_amount_due_leaves_out_cancelled_lines(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, line_states=["shipped", "cancelled"], line_totals=[1500, 700]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        whole = hand_over(client, order, 2200)
        live = hand_over(client, order, 1500)
    assert_problem(whole, 422, "CASH_AMOUNT_MISMATCH")
    assert whole.json()["amount_due"] == usd(1500)
    assert live.status_code == 200, live.text
    status, lines = await states(db_engine, order.order_id)
    assert (status, sorted(lines)) == ("completed", ["cancelled", "delivered"])
    assert [r.amount_cents for r in await _cash_rows(db_engine, order.order_id)] == [1500]


@pytest.mark.parametrize("typed", [0, 999, 1001, 100_000])
async def test_a_wrong_amount_is_a_422_and_changes_nothing(
    typed: int, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = hand_over(client, order, typed)
    assert_problem(response, 422, "CASH_AMOUNT_MISMATCH")
    assert response.json()["amount_due"] == usd(1000)
    assert await states(db_engine, order.order_id) == ("in_progress", ["shipped"])
    assert await effects(db_engine, order.order_id) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    ("fulfillment", "line_states"),
    [
        ("delivery", ["shipped", "ready_to_ship"]),
        ("delivery", ["pending"]),
        ("delivery", ["in_production"]),
        ("pickup", ["ready_for_pickup", "in_production"]),
        ("pickup", ["pending"]),
    ],
)
async def test_a_line_not_yet_ready_is_a_409_and_changes_nothing(
    fulfillment: str, line_states: list[str], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, fulfillment=fulfillment, line_states=line_states)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = hand_over(client, order, 1000 * len(line_states))
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "lines_not_ready"
    status, lines = await states(db_engine, order.order_id)
    assert (status, sorted(lines)) == ("in_progress", sorted(line_states))
    assert await effects(db_engine, order.order_id) == (0, 0, 0, 0, 0)


async def test_a_second_handover_is_a_409_and_records_nothing_more(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert hand_over(client, order, 1000).status_code == 200
        after_first = await effects(db_engine, order.order_id)
        again = hand_over(client, order, 1000)
    assert_problem(again, 409, "INVALID_STATE_TRANSITION")
    assert again.json()["reason"] == "already_recorded"
    assert await effects(db_engine, order.order_id) == after_first
    assert after_first[4] == 1


async def test_an_online_order_and_an_order_with_no_live_line_are_refused(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    online = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["shipped"]
    )
    cancelled = await seed_physical_order(
        db_session, line_states=["cancelled"], order_status="cancelled"
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        not_cash = hand_over(client, online, 1000)
        no_line = hand_over(client, cancelled, 1000)
    for response, reason in ((not_cash, "not_a_cash_order"), (no_line, "no_live_line")):
        assert_problem(response, 409, "INVALID_STATE_TRANSITION")
        assert response.json()["reason"] == reason
    assert await states(db_engine, online.order_id) == ("in_progress", ["shipped"])
    assert await effects(db_engine, cancelled.order_id) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "body",
    [
        {"amount_cents": 1000, "currency": "EUR"},
        {"amount_cents": -1, "currency": "USD"},
        {"amount_cents": 10.0, "currency": "USD"},
        {"amount_cents": "1000", "currency": "USD"},
        {"amount_cents": 1000},
        {"amount_cents": 1000, "currency": "USD", "status": "paid"},
        {"amount_cents": 1000, "currency": "USD", "note": "x" * 501},
    ],
)
async def test_a_malformed_body_is_a_validation_error(
    body: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(handover_path(order.order_id), json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert await effects(db_engine, order.order_id) == (0, 0, 0, 0, 0)


async def test_the_note_is_kept_in_the_history_and_the_audit(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(
            handover_path(order.order_id),
            json={"amount_cents": 1000, "currency": "USD", "note": "  paid in small notes  "},
            headers=csrf(client),
        )
    assert response.status_code == 200, response.text
    reasons = {h["reason"] for h in response.json()["status_history"] if h["order_item_id"]}
    assert reasons == {"paid in small notes"}
    [audit] = await _handover_audits(db_engine, order.order_id)
    assert audit.after_data["note"] == "paid in small notes"


async def test_customers_anonymous_csrf_and_unknown_orders(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id, line_states=["shipped"])
    body = {"amount_cents": 1000, "currency": "USD"}
    with client_for(main_app) as client:
        anonymous = client.post(handover_path(order.order_id), json=body)
        login(client, buyer.email, PASSWORD)
        owner = hand_over(client, order, 1000)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        no_csrf = client.post(handover_path(order.order_id), json=body)
        unknown = client.post(handover_path(uuid.uuid4()), json=body, headers=csrf(client))
    assert_problem(anonymous, 401, "AUTH_REQUIRED")
    assert_problem(owner, 404, "NOT_FOUND")
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    assert_problem(unknown, 404, "NOT_FOUND")
    assert await effects(db_engine, order.order_id) == (0, 0, 0, 0, 0)


async def test_the_customer_sees_the_order_paid_and_completed(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id, line_states=["shipped"])
    me = f"/api/v1/me/orders/{order.order_id}"
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        before = customer.get(me).json()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert hand_over(client, order, 1000).status_code == 200
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        after = customer.get(me).json()
    assert (before["payment_due"], before["amount_due"]) == (True, usd(1000))
    assert before["payment"] is None
    assert (after["status"], after["payment_due"], after["amount_due"]) == (
        "completed",
        False,
        None,
    )
    assert after["payment"] is not None
    assert after["lines"][0]["fulfillment_status"] == "delivered"
    assert "recorded_by" not in str(after)
