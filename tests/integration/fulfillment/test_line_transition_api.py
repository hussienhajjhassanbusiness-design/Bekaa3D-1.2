"""VS-029 over HTTP: physical line transitions (FR-08; SRS 8.3-8.5, 20.4-20.5; BR-148;
ADR-024 d4, d8; ADR-025; ADR-040 d2)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.integrations.email.ports import EmailProviderPort
from app.jobs import outbox as outbox_job
from app.main import app as main_app
from app.ordering.domain.enums import OrderItemStatus
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
    REACHED_PAID,
    effects,
    emails,
    move,
    notifications,
    order_path,
    seed_physical_order,
    states,
    transition_path,
)
from tests.integration.ordering.physical_support import setting

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

DELIVERY_PATH = ["pending", "in_production", "ready_to_ship", "shipped", "delivered"]
PICKUP_PATH = ["pending", "in_production", "ready_for_pickup", "picked_up"]
PATHS = {"delivery": DELIVERY_PATH, "pickup": PICKUP_PATH}
PHYSICAL_STATES = [s.value for s in OrderItemStatus if s is not OrderItemStatus.AWAITING_DELIVERY]


def _payment(payment_method: str) -> str | None:
    return "paid" if payment_method == "online" else None


def _actions(client: TestClient, order_id: uuid.UUID) -> dict[str, list[str]]:
    detail = client.get(order_path(order_id))
    assert detail.status_code == 200, detail.text
    return {
        line["id"]: [a["target_status"] for a in line["available_actions"]]
        for line in detail.json()["lines"]
    }


# --- every legal edge ---------------------------------------------------------------------


@pytest.mark.parametrize("payment_method", ["online", "cash"])
@pytest.mark.parametrize("fulfillment", ["delivery", "pickup"])
async def test_each_legal_edge_moves_the_line_and_lists_the_next_one(
    fulfillment: str, payment_method: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method=payment_method,
        fulfillment=fulfillment,
        payment_status=_payment(payment_method),
    )
    path = PATHS[fulfillment]
    # A cash order stops before the last step: only the handover reaches it.
    steps = path[1:-1] if payment_method == "cash" else path[1:]
    line = str(order.line_ids[0])
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        for step in steps:
            assert _actions(client, order.order_id)[line] == [step]
            response = move(client, order, step)
            assert response.status_code == 200, response.text
            [item] = response.json()["lines"]
            assert item["fulfillment_status"] == step
        final = _actions(client, order.order_id)[line]
    assert final == []
    status, lines = await states(db_engine, order.order_id)
    assert lines == [steps[-1]]
    assert status == ("in_progress" if payment_method == "cash" else "completed")
    async with db_engine.connect() as conn:
        history = (
            await conn.execute(
                text(
                    "SELECT from_status, to_status, actor_user_id FROM order_status_history"
                    " WHERE order_item_id = :i ORDER BY created_at"
                ),
                {"i": order.line_ids[0]},
            )
        ).all()
        audits = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'order_item.transitioned'"
                " AND entity_id = :i"
            ),
            {"i": order.line_ids[0]},
        )
    expected = list(zip([path[0], *steps[:-1]], steps, strict=True))
    assert [(h.from_status, h.to_status) for h in history] == expected
    assert {h.actor_user_id for h in history} == {admin.id}
    assert audits == len(steps)


async def test_an_online_order_completes_and_records_completed_at(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="paid")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        for step in DELIVERY_PATH[1:]:
            assert move(client, order, step).status_code == 200
        detail = client.get(order_path(order.order_id)).json()
    assert detail["status"] == "completed" and detail["completed_at"] is not None


# --- BR-148 and the cash rule -------------------------------------------------------------


@pytest.mark.parametrize("payment_status", [None, "pending", "failed", "expired"])
async def test_no_physical_work_on_an_unpaid_online_order(
    payment_status: str | None, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status=payment_status
    )
    before = await effects(db_engine, order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "in_production")
        actions = _actions(client, order.order_id)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert (response.json()["reason"], response.json()["fulfillment_status"]) == (
        "payment_required",
        "pending",
    )
    assert actions == {str(order.line_ids[0]): []}
    assert await states(db_engine, order.order_id) == ("pending_payment", ["pending"])
    assert await effects(db_engine, order.order_id) == before


@pytest.mark.parametrize("payment_status", ["paid", "partially_refunded", "refunded"])
async def test_every_payment_state_that_reached_paid_opens_the_gate(
    payment_status: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status=payment_status
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "in_production")
    assert response.status_code == 200, response.text
    assert (await states(db_engine, order.order_id))[1] == ["in_production"]


@pytest.mark.parametrize(
    ("fulfillment", "ready", "done"),
    [("delivery", "shipped", "delivered"), ("pickup", "ready_for_pickup", "picked_up")],
)
async def test_a_cash_order_reaches_its_last_step_only_through_the_handover(
    fulfillment: str, ready: str, done: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, fulfillment=fulfillment, line_states=[ready])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, done)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "cash_handover_required"
    assert await states(db_engine, order.order_id) == ("in_progress", [ready])
    assert (await effects(db_engine, order.order_id))[4] == 0


@pytest.mark.parametrize(
    ("fulfillment", "current", "target"),
    [
        ("delivery", "in_production", "ready_for_pickup"),
        ("pickup", "in_production", "ready_to_ship"),
        ("pickup", "ready_for_pickup", "shipped"),
        ("delivery", "pending", "ready_to_ship"),
        ("delivery", "shipped", "returned"),
        ("delivery", "pending", "cancelled"),
        ("delivery", "delivered", "refunded"),
    ],
)
async def test_skipped_cross_method_and_later_slice_edges_are_409s(
    fulfillment: str,
    current: str,
    target: str,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        fulfillment=fulfillment,
        line_states=[current],
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, target)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "not_a_legal_edge"
    assert (await states(db_engine, order.order_id))[1] == [current]


# --- available_actions matches the endpoint (ADR-025) -------------------------------------


@pytest.mark.parametrize("state", PHYSICAL_STATES)
@pytest.mark.parametrize(
    ("payment_method", "payment_status"),
    [
        ("cash", None),
        ("online", "paid"),
        ("online", "partially_refunded"),
        ("online", "refunded"),
        ("online", "failed"),
        ("online", None),
    ],
)
@pytest.mark.parametrize("fulfillment", ["delivery", "pickup"])
async def test_every_listed_action_succeeds_and_every_other_target_is_a_409(
    fulfillment: str,
    payment_method: str,
    payment_status: str | None,
    state: str,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method=payment_method,
        payment_status=payment_status,
        fulfillment=fulfillment,
        line_states=[state],
        order_status="cancelled" if state == "cancelled" else None,
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        detail = client.get(order_path(order.order_id)).json()
        [line] = detail["lines"]
        listed = [a["target_status"] for a in line["available_actions"]]
        assert all(a["cancel_reasons"] == [] for a in line["available_actions"])
        refused = {t: move(client, order, t) for t in PHYSICAL_STATES if t not in listed}
        accepted = {t: move(client, order, t) for t in listed}
    assert {t: r.status_code for t, r in refused.items()} == dict.fromkeys(refused, 409)
    assert {t: r.status_code for t, r in accepted.items()} == dict.fromkeys(accepted, 200)
    assert len(listed) <= 1
    if payment_method == "online" and payment_status not in REACHED_PAID:
        assert listed == []
    if payment_method == "cash":
        assert not set(listed) & {"delivered", "picked_up"}


@pytest.mark.parametrize(
    ("stl_state", "listed"),
    [("pending", []), ("awaiting_delivery", ["delivered"]), ("delivered", [])],
)
async def test_an_stl_line_lists_only_its_own_edge(
    stl_state: str, listed: list[str], db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", stl_line=stl_state
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        lines = client.get(order_path(order.order_id)).json()["lines"]
    [stl] = [line for line in lines if line["product_type"] == "stl"]
    assert [a["target_status"] for a in stl["available_actions"]] == listed


# --- what the customer hears and sees -----------------------------------------------------


async def test_start_printing_is_silent_masked_and_closes_self_cancel(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id)
    me = f"/api/v1/me/orders/{order.order_id}"
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        before = customer.get(me).json()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "in_production").status_code == 200
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        after = customer.get(me).json()
    assert before["can_cancel"] is True and after["can_cancel"] is False
    assert after["lines"][0]["fulfillment_status"] == "pending"
    shown = {(h["from_status"], h["to_status"]) for h in after["status_history"]}
    assert not any("in_production" in pair for pair in shown)
    assert "available_actions" not in after["lines"][0] and "admin_note" not in after
    assert await emails(db_engine, order.order_id) == []
    assert await notifications(db_engine, order.order_id) == []


async def test_a_three_line_delivery_order_hears_once_per_step_on_the_last_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["pending"] * 3
    )
    sent_on: list[tuple[str, int]] = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        for step in DELIVERY_PATH[1:]:
            for line in range(3):
                before = len(await emails(db_engine, order.order_id))
                assert move(client, order, step, line=line).status_code == 200
                if len(await emails(db_engine, order.order_id)) > before:
                    sent_on.append((step, line))
    assert sent_on == [("ready_to_ship", 2), ("shipped", 2), ("delivered", 2)]
    mails = await emails(db_engine, order.order_id)
    assert [m[0] for m in mails] == ["order_ready", "order_shipped", "order_delivered"]
    assert all(m[1]["delivery_fee_note"] for m in mails)
    assert [m[1]["receipt_actions"] for m in mails] == [False, False, True]
    assert await notifications(db_engine, order.order_id) == [
        "order.ready_to_ship",
        "order.shipped",
        "order.delivered",
    ]
    assert not any("phone" in key for m in mails for key in m[1])


async def test_a_pickup_order_is_told_the_workshop_address_and_hours(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        fulfillment="pickup",
        line_states=["in_production", "ready_for_pickup"],
    )
    async with (
        setting(db_engine, "pickup_address", "Workshop, Zahle"),
        setting(db_engine, "pickup_hours", "Mon-Sat 9-17"),
    ):
        with client_for(main_app) as client:
            await mfa_admin(client, db_session)
            assert move(client, order, "ready_for_pickup").status_code == 200
            assert move(client, order, "picked_up", line=1).status_code == 200
            assert move(client, order, "picked_up").status_code == 200
    mails = await emails(db_engine, order.order_id)
    assert [m[0] for m in mails] == ["order_ready_for_pickup", "order_picked_up"]
    ready = mails[0][1]
    assert (ready["pickup_address"], ready["pickup_hours"]) == ("Workshop, Zahle", "Mon-Sat 9-17")
    assert ready["delivery_fee_note"] is None
    assert await notifications(db_engine, order.order_id) == [
        "order.ready_for_pickup",
        "order.picked_up",
    ]


async def test_cancelled_lines_are_not_waited_for(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, line_states=["cancelled", "ready_to_ship", "in_production"]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "ready_to_ship", line=2).status_code == 200
    assert [m[0] for m in await emails(db_engine, order.order_id)] == ["order_ready"]


# --- atomicity, authorization, validation -------------------------------------------------


async def test_a_failing_notice_rolls_the_transition_back(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = await seed_physical_order(db_session, line_states=["in_production"])

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("notification store down")

    monkeypatch.setattr("app.fulfillment.infrastructure.delivery_side.create_notification", boom)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "ready_to_ship")
    assert response.status_code == 500
    assert await states(db_engine, order.order_id) == ("in_progress", ["in_production"])
    assert await effects(db_engine, order.order_id) == (0, 0, 0, 0, 0)


async def test_an_email_outage_does_not_block_a_transition(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = await seed_physical_order(db_session, line_states=["in_production"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "ready_to_ship").status_code == 200

    class Down(EmailProviderPort):
        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("email provider unavailable")

    monkeypatch.setattr(outbox_job, "get_email_provider", lambda settings: Down())
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE email_outbox SET status = 'sent', sent_at = now() WHERE status ="
                " 'pending' AND payload->>'order_id' IS DISTINCT FROM CAST(:o AS text)"
            ),
            {"o": str(order.order_id)},
        )
    await outbox_job.dispatch_outbox({"session_factory": factory})
    assert await states(db_engine, order.order_id) == ("in_progress", ["ready_to_ship"])
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT status, attempt_count FROM email_outbox"
                    " WHERE payload->>'order_id' = CAST(:o AS text)"
                ),
                {"o": str(order.order_id)},
            )
        ).one()
    assert (row.status, row.attempt_count) == ("pending", 1)


async def test_customers_anonymous_and_admins_without_mfa_never_reach_a_transition(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id)
    no_mfa = await create_user(db_session, role=UserRole.ADMIN)
    path = transition_path(order.order_id, order.line_ids[0])
    body = {"target_status": "in_production"}
    with client_for(main_app) as anonymous:
        assert anonymous.post(path, json=body).status_code == 401
    with client_for(main_app) as customer:
        login(customer, buyer.email, PASSWORD)
        assert customer.post(path, json=body, headers=csrf(customer)).status_code == 404
    with client_for(main_app) as admin:
        login(admin, no_mfa.email, PASSWORD)
        assert admin.post(path, json=body, headers=csrf(admin)).status_code == 401
    assert (await states(db_engine, order.order_id))[1] == ["pending"]


async def test_a_transition_needs_csrf_and_a_foreign_line_is_a_404(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session)
    other = await seed_physical_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        no_csrf = client.post(
            transition_path(order.order_id, order.line_ids[0]),
            json={"target_status": "in_production"},
        )
        foreign = client.post(
            transition_path(order.order_id, other.line_ids[0]),
            json={"target_status": "in_production"},
            headers=csrf(client),
        )
        extra = move(client, order, "in_production", cancel_reason="other")
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    assert_problem(foreign, 404, "NOT_FOUND")
    assert_problem(extra, 422, "VALIDATION_ERROR")
    assert (await states(db_engine, order.order_id))[1] == ["pending"]
    assert (await states(db_engine, other.order_id))[1] == ["pending"]


async def test_the_note_is_kept_in_the_history_and_the_audit(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "in_production", reason="  Called the customer  ")
    assert response.status_code == 200
    history = response.json()["status_history"]
    assert [h["reason"] for h in history if h["order_item_id"]] == ["Called the customer"]
    async with db_engine.connect() as conn:
        note = await conn.scalar(
            text("SELECT after_data->>'note' FROM audit_logs WHERE entity_id = :i"),
            {"i": order.line_ids[0]},
        )
    assert note == "Called the customer"


async def test_a_mixed_order_keeps_its_stl_line_queued_while_the_physical_line_moves(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", stl_line="awaiting_delivery"
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        for step in DELIVERY_PATH[1:]:
            assert move(client, order, step).status_code == 200
        queued = client.get("/api/v1/admin/stl-deliveries", params={"limit": 100}).json()
    assert await states(db_engine, order.order_id) == ("in_progress", ["delivered"])
    assert str(order.order_id) in {item["order_id"] for item in queued["items"]}
