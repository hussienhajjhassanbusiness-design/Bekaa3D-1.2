"""VS-031's mixed-order paths (the SRS's most bug-prone area): a physical line's cancellation
refund beside the STL line's refunds, and a chargeback for the whole payment after a cancel
(must-resolve 2, ADR-043). Statuses are (order, payment)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import assert_problem, client_for, mfa_admin
from tests.integration.fulfillment.cancel_support import admin_cancel, refunds_of
from tests.integration.fulfillment.order_support import PhysicalOrder, move
from tests.integration.payments.refund_support import (
    Paid,
    act,
    chargeback,
    create,
    line_state,
    ok,
    paid_online,
    payment_of,
    statuses,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

PART = ("partially_refunded", "partially_refunded")
FULL = ("refunded", "refunded")


def _as_order(paid: Paid) -> PhysicalOrder:
    return PhysicalOrder(paid.order_id, paid.user_id, "", paid.physical, paid.phone)


async def _mixed(db: AsyncSession, physical: str = "in_production", stl: str = "delivered") -> Paid:
    order = await paid_online(db, physical=(physical,), stl=stl)
    assert order.stl is not None
    return order


async def test_a_cancellation_then_the_stl_refund_reads_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(admin_cancel(client, order.order_id))
        assert await statuses(db_engine, order.order_id) == PART
        assert order.stl is not None
        ok(create(client, order.order_id, [(order.stl, 500)]), 201)
    assert await statuses(db_engine, order.order_id) == FULL


async def test_the_stl_refunded_first_then_a_started_line_cancelled_reads_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """BR-148: a payment already partially refunded still opens the gate."""
    order = await _mixed(db_session, physical="pending")
    assert order.stl is not None
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 500)]), 201)
        assert move(client, _as_order(order), "in_production").status_code == 200
        ok(admin_cancel(client, order.order_id))
    assert await statuses(db_engine, order.order_id) == FULL
    assert [r.amount_cents for r in await refunds_of(db_engine, order.order_id)] == [500, 1000]


async def test_a_returned_line_refunded_beside_a_delivered_stl_reads_partially_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session, physical="returned")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(order.physical[0], 1000)]), 201)
    assert await line_state(db_engine, order.physical[0]) == "refunded"
    assert await statuses(db_engine, order.order_id) == PART


async def test_after_a_cancellation_the_stl_balance_is_exact_to_the_cent(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session)
    assert order.stl is not None
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(admin_cancel(client, order.order_id))
        over = create(client, order.order_id, [(order.stl, 501)])
        on_cancelled = create(client, order.order_id, [(order.physical[0], 1)])
        exact = create(client, order.order_id, [(order.stl, 500)])
    assert_problem(over, 422, "REFUND_EXCEEDS_AVAILABLE")
    assert_problem(on_cancelled, 422, "REFUND_EXCEEDS_AVAILABLE")
    assert exact.status_code == 201, exact.text
    assert await statuses(db_engine, order.order_id) == FULL


async def test_a_partial_stl_refund_then_a_full_cancellation_stays_partially_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session)
    assert order.stl is not None
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 200)]), 201)
        ok(admin_cancel(client, order.order_id))
    assert await statuses(db_engine, order.order_id) == PART


async def test_a_failed_cancellation_refund_stays_owed_and_never_completes(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(admin_cancel(client, order.order_id))
        [refund] = await refunds_of(db_engine, order.order_id)
        ok(act(client, refund.id, "fail", {"reason": "The card was closed."}))
        queue = ok(client.get("/api/v1/admin/refunds", params={"order_id": str(order.order_id)}))
    assert await statuses(db_engine, order.order_id) == PART
    assert [item["id"] for item in queue["items"]] == [str(refund.id)]


async def test_a_cancellation_refund_on_a_cancelled_line_is_never_voided(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await _mixed(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(admin_cancel(client, order.order_id))
        [refund] = await refunds_of(db_engine, order.order_id)
        response = act(client, refund.id, "void", {"reason": "Mistake."})
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "line_already_cancelled"


# --- must-resolve 2: a chargeback for the whole payment after a cancel ---------------------


def _cancel_after_goodwill(client: TestClient, order: Paid) -> None:
    ok(create(client, order.order_id, [(order.physical[0], 300)]), 201)
    ok(admin_cancel(client, order.order_id))


async def test_a_chargeback_for_the_whole_payment_after_a_cancel_is_satisfiable(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The cancel covered the line's whole balance (300 goodwill + 700), so the chargeback
    absorbs both and only the STL's 500 is left for the administrator's items."""
    order = await _mixed(db_session)
    assert order.stl is not None
    payment_id = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        _cancel_after_goodwill(client, order)
        wrong = chargeback(client, order.order_id, payment_id, 1500, [])
        recorded = chargeback(client, order.order_id, payment_id, 1500, [(order.stl, 500)])
    assert_problem(wrong, 422, "CHARGEBACK_ALLOCATION_INVALID")
    assert wrong.json()["available"]["chargeable_cents"] == 500
    body = ok(recorded, 201)
    assert (body["applied_cents"], body["excess_cents"]) == (1500, 0)
    assert await statuses(db_engine, order.order_id) == FULL
    assert await line_state(db_engine, order.physical[0]) == "cancelled"
    assert await line_state(db_engine, order.stl) == "refunded"


async def test_a_physical_only_order_charged_back_after_a_cancel_needs_no_items(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, physical=("pending", "in_production"), stl=None)
    payment_id = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        _cancel_after_goodwill(client, order)
        recorded = chargeback(client, order.order_id, payment_id, 2000, [])
    body = ok(recorded, 201)
    assert (body["applied_cents"], body["excess_cents"]) == (2000, 0)
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
