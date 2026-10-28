"""VS-031 over HTTP: the administrator's order cancel and the transition endpoint's cancel and
return edges (FR-08, FR-09, FR-20; BR-144, BR-148, BR-149; SRS 20.4-20.5; ADR-043)."""

import os
import uuid
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import hash_phone
from app.fulfillment.domain.limits import STL_DELIVERY_RATE_LIMIT
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.cancel_support import (
    admin_cancel,
    blocks_of,
    cancel_audits,
    cancel_history,
    reasons_of,
    refunds_of,
)
from tests.integration.fulfillment.order_support import (
    ORDERS,
    PhysicalOrder,
    effects,
    emails,
    hand_over,
    move,
    notifications,
    order_path,
    seed_physical_order,
    states,
)
from tests.integration.payments.refund_support import create, paid_cash, statuses

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _cancel_line(
    client: TestClient, order: PhysicalOrder, line: int, reason: str | None = None
) -> Any:
    extra = {} if reason is None else {"cancel_reason": reason}
    return move(client, order, "cancelled", line=line, **extra)


# --- the order cancel ----------------------------------------------------------------------


@pytest.mark.parametrize("state", ["pending", "in_production"])
async def test_an_admin_cancel_of_a_paid_line_refunds_its_whole_balance(
    state: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=[state]
    )
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        assert create(client, order.order_id, [(order.line_ids[0], 250)]).status_code == 201
        response = admin_cancel(client, order.order_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
    _, cancellation = await refunds_of(db_engine, order.order_id)
    assert (cancellation.kind, cancellation.amount_cents) == ("cancellation", 750)
    assert (cancellation.requested_by, cancellation.approved_by) == (admin.id, admin.id)
    [audit] = await cancel_audits(db_engine, order.order_id)
    assert audit.actor_user_id == admin.id
    assert audit.after_data["by"] == "administrator"
    assert audit.after_data["lines"] == [
        {"order_item_id": str(order.line_ids[0]), "from_status": state, "cancel_reason": None}
    ]
    assert audit.after_data["has_note"] is True and "note" not in audit.after_data
    line = order.line_ids[0]
    assert await cancel_history(db_engine, order.order_id) == {
        (line, state, admin.id, "Printer failure")
    }
    shown = [
        (h["order_item_id"], h["from_status"], h["actor_user_id"], h["reason"])
        for h in response.json()["status_history"]
        if h["to_status"] == "cancelled" and h["order_item_id"] is not None
    ]
    assert shown == [(str(line), state, str(admin.id), "Printer failure")]


async def test_the_admin_cancel_shares_the_transition_rate_limit(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-043 d11: one per-administrator budget for transitions and cancels (A-05)."""
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["pending"] * 2
    )
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
        key = f"ratelimit:admin_stl_delivery:{admin.id}"
        await store.set(key, STL_DELIVERY_RATE_LIMIT - 1, ex=3600)
        await store.aclose()
        moved = move(client, order, "in_production", line=0)
        refused = admin_cancel(client, order.order_id)
    assert moved.status_code == 200, moved.text
    assert_problem(refused, 429, "RATE_LIMITED")
    assert sorted((await states(db_engine, order.order_id))[1]) == ["in_production", "pending"]
    assert await refunds_of(db_engine, order.order_id) == []


async def test_an_admin_cancel_leaves_stl_and_later_lines_alone(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["in_production", "shipped"],
        stl_line="awaiting_delivery",
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = admin_cancel(client, order.order_id)
    assert response.status_code == 200, response.text
    status, lines = await states(db_engine, order.order_id)
    assert (status, sorted(lines)) == ("partially_refunded", ["cancelled", "shipped"])
    stl = [line for line in response.json()["lines"] if line["product_type"] == "stl"]
    assert stl[0]["fulfillment_status"] == "awaiting_delivery"


@pytest.mark.parametrize(
    ("seed", "cancel_reason", "refusal"),
    [
        ({"payment_method": "online", "payment_status": None}, None, "payment_required"),
        ({"payment_method": "online", "payment_status": "pending"}, None, "payment_required"),
        ({"line_states": ["shipped", "returned"]}, None, "no_cancellable_line"),
        ({"line_states": ["ready_to_ship"]}, None, "cancel_reason_required"),
        ({"line_states": ["ready_to_ship"]}, "no_show", "cancel_reason_not_allowed"),
        ({"line_states": ["pending"]}, "refused", "cancel_reason_not_allowed"),
    ],
)
async def test_an_admin_cancel_that_cannot_occur_is_a_409_and_changes_nothing(
    seed: dict[str, Any],
    cancel_reason: str | None,
    refusal: str,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    order = await seed_physical_order(db_session, **seed)
    before = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = admin_cancel(client, order.order_id, cancel_reason)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == refusal
    after = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))
    assert after == before
    assert await blocks_of(db_engine, order.order_id) == []


async def test_the_admin_cancel_sits_behind_the_admin_boundary_and_csrf(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session)
    customer = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, customer.email)
        as_customer = admin_cancel(client, order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        no_csrf = client.post(f"{ORDERS}/{order.order_id}/cancel", json={"reason": "x"})
        no_reason = client.post(f"{ORDERS}/{order.order_id}/cancel", json={}, headers=csrf(client))
        unknown = admin_cancel(client, uuid.uuid4())
    assert_problem(as_customer, 404, "NOT_FOUND")
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    assert_problem(no_reason, 422, "VALIDATION_ERROR")
    assert_problem(unknown, 404, "NOT_FOUND")
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])


# --- BR-144: the cash block ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fulfillment", "state", "reason"),
    [
        ("delivery", "ready_to_ship", "refused"),
        ("pickup", "ready_for_pickup", "refused"),
        ("pickup", "ready_for_pickup", "no_show"),
    ],
)
async def test_a_whole_cash_order_refused_or_not_collected_blocks_cash(
    fulfillment: str, state: str, reason: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, fulfillment=fulfillment, line_states=[state])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = admin_cancel(client, order.order_id, reason)
    assert response.status_code == 200, response.text
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled"])
    assert await refunds_of(db_engine, order.order_id) == []
    [block] = await blocks_of(db_engine, order.order_id)
    assert (block.user_id, block.contact_phone_hash) == (order.user_id, hash_phone(order.phone))
    assert block.reason == reason
    [audit] = await cancel_audits(db_engine, order.order_id)
    assert audit.after_data["cash_block"] is True
    assert "phone" not in str(audit.after_data)


async def test_a_pickup_no_show_on_an_online_order_refunds_and_never_blocks(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        fulfillment="pickup",
        line_states=["ready_for_pickup"],
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _cancel_line(client, order, 0, "no_show")
    assert response.status_code == 200, response.text
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
    assert [r.amount_cents for r in await refunds_of(db_engine, order.order_id)] == [1000]
    assert await blocks_of(db_engine, order.order_id) == []
    assert await reasons_of(db_engine, order.order_id) == ["no_show"]


@pytest.mark.parametrize(
    ("first", "second", "blocked"),
    [
        ("refused", "other", False),
        ("other", "refused", False),
        ("refused", "refused", True),
    ],
)
async def test_the_block_is_the_same_whatever_the_cancel_order(
    first: str, second: str, blocked: bool, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["ready_to_ship"] * 2)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert _cancel_line(client, order, 0, first).status_code == 200
        assert await blocks_of(db_engine, order.order_id) == []  # a line is still live
        assert _cancel_line(client, order, 1, second).status_code == 200
    assert bool(await blocks_of(db_engine, order.order_id)) is blocked
    assert (await states(db_engine, order.order_id))[0] == "cancelled"


async def test_an_other_cancel_of_a_whole_cash_order_never_blocks(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["ready_to_ship", "pending"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert admin_cancel(client, order.order_id, "other").status_code == 200
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled", "cancelled"])
    assert set(await reasons_of(db_engine, order.order_id)) == {"other", None}
    assert await blocks_of(db_engine, order.order_id) == []


async def test_a_partly_refused_cash_order_hands_over_the_rest_and_never_blocks(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped", "shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "returned").status_code == 200
        cancelled = _cancel_line(client, order, 0, "refused")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["amount_due"]["amount_cents"] == 1000
        handover = hand_over(client, order, 1000)
    assert handover.status_code == 200, handover.text
    status, lines = await states(db_engine, order.order_id)
    assert (status, sorted(lines)) == ("completed", ["cancelled", "delivered"])
    assert await blocks_of(db_engine, order.order_id) == []
    mails = await emails(db_engine, order.order_id)
    cancel_mail = next(payload for template, payload in mails if template == "order_cancelled")
    assert (cancel_mail["order_cancelled"], cancel_mail["amount_due_cents"]) == (False, 1000)


async def test_a_refusal_that_leaves_only_zero_lines_ends_cancelled_without_a_handover(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, line_states=["ready_to_ship", "shipped"], line_totals=[1000, 0]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert _cancel_line(client, order, 0, "refused").status_code == 200
        zero = _cancel_line(client, order, 1, "other")
        assert zero.status_code == 200, zero.text
        handover = hand_over(client, order, 0)
    assert_problem(handover, 409, "INVALID_STATE_TRANSITION")
    assert handover.json()["reason"] == "no_live_line"
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled", "cancelled"])
    assert await blocks_of(db_engine, order.order_id) == []
    assert (await effects(db_engine, order.order_id))[4] == 0


async def test_a_shipped_zero_cash_line_is_cancelled_without_a_return(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"], line_totals=[0])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        listed = client.get(order_path(order.order_id)).json()["lines"][0]["available_actions"]
        missing = _cancel_line(client, order, 0)
        done = _cancel_line(client, order, 0, "other")
    assert {"target_status": "cancelled", "cancel_reasons": ["other"]} in listed
    assert missing.json()["reason"] == "cancel_reason_required"
    assert done.status_code == 200, done.text
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled"])
    assert await reasons_of(db_engine, order.order_id) == ["other"]


# --- returns and illegal edges --------------------------------------------------------------


async def test_a_returned_cash_line_is_cancelled_with_no_refund(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "returned").status_code == 200
        refund = create(client, order.order_id, [(order.line_ids[0], 1000)])
        transition = move(client, order, "refunded")
        assert _cancel_line(client, order, 0, "refused").status_code == 200
    assert_problem(refund, 409, "ORDER_NOT_PAID")
    assert_problem(transition, 409, "INVALID_STATE_TRANSITION")
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled"])
    assert await refunds_of(db_engine, order.order_id) == []
    assert len(await blocks_of(db_engine, order.order_id)) == 1


async def test_a_returned_paid_line_is_never_cancelled_and_is_refunded_instead(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["returned"],
        stl_line="delivered",
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refused = _cancel_line(client, order, 0, "refused")
        refunded = create(client, order.order_id, [(order.line_ids[0], 1000)])
    assert_problem(refused, 409, "INVALID_STATE_TRANSITION")
    assert refused.json()["reason"] == "not_a_legal_edge"
    assert refunded.status_code == 201, refunded.text
    assert await states(db_engine, order.order_id) == ("partially_refunded", ["refunded"])


@pytest.mark.parametrize("target", ["shipped", "in_production"])
async def test_a_returned_line_is_reshipped_or_reprinted(
    target: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["shipped"]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert move(client, order, "returned").status_code == 200
        assert move(client, order, target).status_code == 200
    assert (await states(db_engine, order.order_id))[1] == [target]
    shipped = [n for n in await notifications(db_engine, order.order_id) if n == "order.shipped"]
    assert len(shipped) == (1 if target == "shipped" else 0)  # a re-ship is announced again


async def test_a_refund_item_on_a_cancelled_line_of_a_paid_cash_order_is_a_422(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_cash(db_session, lines=("cancelled", "delivered"))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = create(client, order.order_id, [(order.physical[0], 1)])
    assert_problem(response, 422, "REFUND_EXCEEDS_AVAILABLE")
    assert await refunds_of(db_engine, order.order_id) == []


# --- notices ---------------------------------------------------------------------------------


async def test_a_cancel_that_leaves_the_rest_at_a_step_announces_it_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["ready_to_ship", "in_production", "ready_to_ship"],
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert _cancel_line(client, order, 1).status_code == 200
        assert _cancel_line(client, order, 2, "other").status_code == 200
    templates = [m[0] for m in await emails(db_engine, order.order_id)]
    assert templates.count("order_ready") == 1
    assert templates.count("order_cancelled") == 2


async def test_available_actions_list_the_cancel_reasons(db_session: AsyncSession) -> None:
    order = await seed_physical_order(
        db_session, fulfillment="pickup", line_states=["ready_for_pickup"]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        [line] = client.get(order_path(order.order_id)).json()["lines"]
    assert line["available_actions"] == [
        {"target_status": "cancelled", "cancel_reasons": ["refused", "no_show", "other"]}
    ]


async def test_a_mixed_pickup_order_not_collected_refunds_the_physical_line_only(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-024 appendix: `ready_for_pickup -> cancelled` with a refund, beside an STL line."""
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        fulfillment="pickup",
        line_states=["ready_for_pickup"],
        stl_line="awaiting_delivery",
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = admin_cancel(client, order.order_id, "no_show")
    assert response.status_code == 200, response.text
    assert await statuses(db_engine, order.order_id) == (
        "partially_refunded",
        "partially_refunded",
    )
    [refund] = await refunds_of(db_engine, order.order_id)
    assert refund.items == {str(order.line_ids[0]): 1000}
    stl = [line for line in response.json()["lines"] if line["product_type"] == "stl"]
    assert stl[0]["fulfillment_status"] == "awaiting_delivery"
    assert await blocks_of(db_engine, order.order_id) == []
