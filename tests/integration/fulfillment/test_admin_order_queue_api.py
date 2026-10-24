"""VS-029 over HTTP: the admin order queue, detail and internal note (SRS 8.7, 15.2; F-060,
F-062; BR-148; ADR-025; ADR-040)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.ordering.domain.admin_orders import AdminOrderFilters
from app.ordering.infrastructure.admin_orders import admin_queue_query
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
    ORDERS,
    PhysicalOrder,
    order_path,
    seed_physical_order,
)
from tests.integration.ordering.physical_support import usd

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

NOTE = "Customer is a friend of the owner - call before shipping"
T0 = datetime(2026, 10, 1, 9, tzinfo=UTC)


def _ids(client: TestClient, **params: Any) -> list[str]:
    response = client.get(ORDERS, params=params)
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _mixed_orders(db: AsyncSession, user_id: uuid.UUID) -> dict[str, PhysicalOrder]:
    """One order per queue-relevant kind, an hour apart, the newest last."""
    kinds: dict[str, dict[str, Any]] = {
        "unpaid_online": {"payment_method": "online", "payment_status": "pending"},
        "no_attempt_online": {"payment_method": "online"},
        "released_online": {
            "payment_method": "online",
            "payment_status": "expired",
            "line_states": ["cancelled"],
            "order_status": "cancelled",
        },
        "paid_online": {"payment_method": "online", "payment_status": "paid"},
        "cash_due": {"line_totals": [1500, 700], "line_states": ["pending", "cancelled"]},
        "cash_pickup": {"fulfillment": "pickup"},
        "cash_completed": {"line_states": ["delivered"], "order_status": "completed"},
        "cash_cancelled": {"line_states": ["cancelled"], "order_status": "cancelled"},
    }
    seeded = {}
    for hour, (name, kind) in enumerate(kinds.items()):
        at = T0 + timedelta(hours=hour)
        seeded[name] = await seed_physical_order(db, user_id=user_id, placed_at=at, **kind)
    # A completed cash order has its cash; the seed writes no payment for it.
    await db.execute(
        text(
            "INSERT INTO payments (order_id, provider, order_payment_method, status,"
            " amount_cents, initiated_at, verified_at, recorded_by)"
            " VALUES (:o, 'cash', 'cash', 'paid', 1000, :t, :t, :a)"
        ),
        {
            "o": seeded["cash_completed"].order_id,
            "t": T0,
            "a": (await create_user(db)).id,
        },
    )
    await db.commit()
    return seeded


async def test_the_queue_never_lists_an_unpaid_online_order(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    seeded = await _mixed_orders(db_session, buyer.id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        listed = _ids(client, customer_id=str(buyer.id))
        unpaid = client.get(order_path(seeded["unpaid_online"].order_id))
    expected = [
        "cash_cancelled",
        "cash_completed",
        "cash_pickup",
        "cash_due",
        "paid_online",
    ]
    assert listed == [str(seeded[name].order_id) for name in expected]
    # A detail is not the queue: an unpaid online order opens, with no action on its lines.
    assert unpaid.status_code == 200
    assert unpaid.json()["payment_reached_paid"] is False
    assert all(line["available_actions"] == [] for line in unpaid.json()["lines"])


async def test_the_pending_payment_status_filter_is_a_validation_error(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(ORDERS, params={"status": "pending_payment"})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_each_filter_narrows_the_queue(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    seeded = await _mixed_orders(db_session, buyer.id)
    mine = {"customer_id": str(buyer.id)}

    def ids(*names: str) -> list[str]:
        return [str(seeded[n].order_id) for n in names]

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        got = {
            "due": _ids(client, payment_due="true", **mine),
            "not_due": _ids(client, payment_due="false", **mine),
            "online": _ids(client, payment_method="online", **mine),
            "pickup": _ids(client, fulfillment_method="pickup", **mine),
            "completed": _ids(client, status="completed", **mine),
            "number": _ids(client, order_number=seeded["cash_pickup"].order_number),
            "window": _ids(
                client,
                placed_after=(T0 + timedelta(hours=3)).isoformat(),
                placed_before=(T0 + timedelta(hours=5)).isoformat(),
                **mine,
            ),
        }
        due_page = client.get(ORDERS, params={"payment_due": "true", **mine}).json()
    assert got == {
        "due": ids("cash_pickup", "cash_due"),
        "not_due": ids("cash_cancelled", "cash_completed", "paid_online"),
        "online": ids("paid_online"),
        "pickup": ids("cash_pickup"),
        "completed": ids("cash_completed"),
        "number": ids("cash_pickup"),
        "window": ids("cash_due", "paid_online"),
    }
    by_id = {item["id"]: item for item in due_page["items"]}
    cash_due = by_id[str(seeded["cash_due"].order_id)]
    assert (cash_due["payment_due"], cash_due["amount_due"]) == (True, usd(1500))
    assert cash_due["total"] == usd(2200)
    assert "contact_phone" not in cash_due and "admin_note" not in cash_due


async def test_the_queue_pages_newest_first_without_gaps(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    orders = [
        await seed_physical_order(db_session, user_id=buyer.id, placed_at=T0 + timedelta(minutes=i))
        for i in range(5)
    ]
    seen: list[str] = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        cursor = None
        for _ in range(4):
            params = {"customer_id": str(buyer.id), "limit": 2} | (
                {"cursor": cursor} if cursor else {}
            )
            page = client.get(ORDERS, params=params).json()
            seen += [item["id"] for item in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        bad = client.get(ORDERS, params={"cursor": "not-a-cursor"})
        too_many = client.get(ORDERS, params={"limit": 101})
    assert seen == [str(o.order_id) for o in reversed(orders)]
    assert_problem(bad, 422, "VALIDATION_ERROR")
    assert_problem(too_many, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("filters", "index"),
    [
        (AdminOrderFilters(), "ix_orders_admin_queue"),
        (AdminOrderFilters(payment_due=True), "ix_orders_cash_due"),
    ],
)
async def test_the_queue_query_uses_its_partial_index(
    filters: AdminOrderFilters, index: str, db_engine: AsyncEngine
) -> None:
    query = admin_queue_query(filters, after=None, limit=26)
    compiled = query.compile(compile_kwargs={"render_postcompile": True})
    async with db_engine.connect() as conn:
        await conn.execute(text("ANALYZE orders, order_items"))
        await conn.commit()
        await conn.execute(text("SET LOCAL enable_seqscan = off"))
        rows = await conn.execute(text(f"EXPLAIN {compiled}"), dict(compiled.params))
        plan = "\n".join(str(row[0]) for row in rows)
        await conn.rollback()
    assert index in plan, plan


# --- detail ---------------------------------------------------------------------------------


async def test_the_detail_shows_what_only_the_administrator_may_see(
    db_session: AsyncSession,
) -> None:
    order = await seed_physical_order(db_session, line_states=["ready_to_ship"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        body = client.get(order_path(order.order_id)).json()
    assert body["contact_phone"] == order.phone
    assert body["delivery_address"]["recipient_name"] == "Rana"
    assert body["delivery_fee_note"]
    assert (body["payment_due"], body["amount_due"]) == (True, usd(1000))
    assert body["payments"] == []
    [line] = body["lines"]
    assert line["fulfillment_status"] == "ready_to_ship"
    assert line["available_actions"] == [
        {"target_status": "shipped", "cancel_reasons": []},
        {"target_status": "cancelled", "cancel_reasons": ["refused", "other"]},  # VS-031
    ]


async def test_an_unknown_order_is_a_404(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(order_path(uuid.uuid4()))
    assert_problem(response, 404, "NOT_FOUND")


# --- internal note --------------------------------------------------------------------------


def _patch(client: TestClient, order_id: uuid.UUID, body: dict[str, Any]) -> Any:
    return client.patch(order_path(order_id), json=body, headers=csrf(client))


async def test_the_note_is_set_cleared_and_audited_without_its_text(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        written = _patch(client, order.order_id, {"admin_note": f"  {NOTE}  "})
        cleared = _patch(client, order.order_id, {"admin_note": "   "})
    assert written.status_code == 200, written.text
    assert written.json()["admin_note"] == NOTE
    assert cleared.json()["admin_note"] is None
    assert cleared.json()["status"] == "in_progress"
    async with db_engine.connect() as conn:
        audits = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, after_data, CAST(after_data AS text) AS raw"
                    " FROM audit_logs WHERE action = 'order.admin_note_updated'"
                    " AND entity_id = :o ORDER BY created_at"
                ),
                {"o": order.order_id},
            )
        ).all()
        history = await conn.scalar(
            text("SELECT count(*) FROM order_status_history WHERE order_id = :o"),
            {"o": order.order_id},
        )
    assert [a.after_data for a in audits] == [{"has_note": True}, {"has_note": False}]
    assert {a.actor_user_id for a in audits} == {admin.id}
    assert not any("friend" in a.raw for a in audits)
    assert history == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"admin_note": "x" * 5001},
        {"admin_note": "ok", "status": "completed"},
        {"admin_note": "ok", "customer_note": "changed"},
    ],
)
async def test_only_the_note_can_be_patched(body: dict[str, Any], db_session: AsyncSession) -> None:
    order = await seed_physical_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, order.order_id, body)
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_a_patch_needs_csrf_and_an_existing_order(db_session: AsyncSession) -> None:
    order = await seed_physical_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        no_csrf = client.patch(order_path(order.order_id), json={"admin_note": NOTE})
        unknown = _patch(client, uuid.uuid4(), {"admin_note": NOTE})
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    assert_problem(unknown, 404, "NOT_FOUND")


async def test_the_internal_note_is_never_visible_to_the_customer(
    db_session: AsyncSession,
) -> None:
    buyer = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert _patch(client, order.order_id, {"admin_note": NOTE}).status_code == 200
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        listing = customer.get("/api/v1/me/orders")
        detail = customer.get(f"/api/v1/me/orders/{order.order_id}")
        admin_routes = [
            customer.get(ORDERS).status_code,
            customer.get(order_path(order.order_id)).status_code,
            _patch(customer, order.order_id, {"admin_note": "mine"}).status_code,
        ]
    for response in (listing, detail):
        assert response.status_code == 200
        assert "friend of the owner" not in response.text
        assert "admin_note" not in response.text
    assert admin_routes == [404, 404, 404]


async def test_a_paid_order_whose_lines_are_all_cancelled_is_still_listed(
    db_session: AsyncSession,
) -> None:
    """Only the hold release sets `cancelled_at` on an online order (ADR-040 d8)."""
    buyer = await create_user(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=buyer.id,
        payment_method="online",
        payment_status="paid",
        line_states=["cancelled"],
        order_status="cancelled",
    )
    await db_session.execute(
        text("UPDATE orders SET cancelled_at = NULL WHERE id = :o"), {"o": order.order_id}
    )
    await db_session.commit()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        listed = _ids(client, customer_id=str(buyer.id))
    assert listed == [str(order.order_id)]
