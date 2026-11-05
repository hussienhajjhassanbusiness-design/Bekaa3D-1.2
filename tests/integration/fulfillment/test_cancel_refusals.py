"""ADR-043 d1's refusal path on all three cancel routes: when the cancel's refund cannot be
created, nothing is cancelled, nothing is written but the alert, and the administrators
hear of it. Also the guards behind the cancel writer and BR-144's literal rule."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.main import app as main_app
from app.ordering.public import (
    NO_REFUNDS,
    InvalidLineTransitionError,
    LineCancel,
    OrderItemStatus,
    cancel_lines,
    lock_order_for_change,
    transition_physical_line,
)
from app.payments.domain.exceptions import RefundExceedsAvailableError
from app.payments.domain.refunds import Ledger
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.cancel_support import (
    admin_cancel,
    as_customer,
    blocks_of,
    customer_cancel,
    customer_cancelled_at,
    refunds_of,
)
from tests.integration.fulfillment.order_support import (
    PhysicalOrder,
    effects,
    move,
    seed_physical_order,
    states,
)
from tests.integration.payments.refund_support import count

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _mismatched(db: AsyncSession, user_id: uuid.UUID) -> PhysicalOrder:
    """A paid order whose total no longer matches its lines (Q-2)."""
    order = await seed_physical_order(
        db, user_id=user_id, payment_method="online", payment_status="paid"
    )
    await db.execute(
        text(
            "UPDATE orders SET subtotal_cents = subtotal_cents + 1,"
            " total_cents = total_cents + 1 WHERE id = :o"
        ),
        {"o": order.order_id},
    )
    await db.commit()
    return order


async def _alerts(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    return await count(
        engine,
        "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
        " AND after_data->>'kind' = 'refund_integrity' AND after_data->>'order_id' = :o",
        o=str(order_id),
    )


async def _unchanged(engine: AsyncEngine, order: PhysicalOrder, before: Any) -> None:
    assert await states(engine, order.order_id) == ("in_progress", ["pending"])
    history, audits, _, _, cash = await effects(engine, order.order_id)
    assert (history, audits, cash) == (before[0], before[1], before[4])  # the alert notifies
    assert await refunds_of(engine, order.order_id) == []
    assert await customer_cancelled_at(engine, order.order_id) is None


def _over_the_balance(ledger: Ledger, *args: Any, **kwargs: Any) -> None:
    raise RefundExceedsAvailableError(lines={}, payment_cents=0, payment_id=ledger.payment.id)


@pytest.mark.parametrize("route", ["customer", "admin_order", "transition"])
async def test_a_cancel_whose_refund_fails_q2_changes_nothing_and_alerts(
    route: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    order = await _mismatched(db_session, buyer.id)
    before = await effects(db_engine, order.order_id)
    if route == "customer":
        response = as_customer(buyer.email, lambda c: customer_cancel(c, order.order_id))
        assert_problem(response, 409, "ORDER_NOT_CANCELLABLE")
    else:
        with client_for(main_app) as client:
            await mfa_admin(client, db_session)
            if route == "admin_order":
                response = admin_cancel(client, order.order_id)
            else:
                response = move(client, order, "cancelled")
        assert_problem(response, 409, "ORDER_TOTAL_MISMATCH")
    await _unchanged(db_engine, order, before)
    assert await _alerts(db_engine, order.order_id) == 1


async def test_a_refund_beyond_the_payments_balance_refuses_the_customers_cancel(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L5 inside the cancel: the whole cancel is refused, never a partly covered line."""
    buyer = await create_user(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, payment_method="online", payment_status="paid"
    )
    monkeypatch.setattr(
        "app.payments.application.services.refunds.check_request", _over_the_balance
    )
    before = await effects(db_engine, order.order_id)
    with client_for(main_app) as client:
        login(client, buyer.email)
        response = customer_cancel(client, order.order_id)
    assert_problem(response, 409, "ORDER_NOT_CANCELLABLE")
    await _unchanged(db_engine, order, before)
    assert await _alerts(db_engine, order.order_id) == 1


@pytest.mark.parametrize(
    ("route", "shown"), [("transition", {"fulfillment_status": "pending"}), ("admin_order", {})]
)
async def test_a_refund_beyond_the_balance_names_the_line_state_only_for_one_line(
    route: str,
    shown: dict[str, str],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VS-023b audit Q-6: the transition promises the state; a whole-order cancel has no one
    line to name. Both still refuse everything and raise the integrity alert."""
    order = await seed_physical_order(db_session, payment_method="online", payment_status="paid")
    monkeypatch.setattr(
        "app.payments.application.services.refunds.check_request", _over_the_balance
    )
    before = await effects(db_engine, order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        if route == "transition":
            response = move(client, order, "cancelled")
        else:
            response = admin_cancel(client, order.order_id)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "refund_exceeds_available"
    assert {k: v for k, v in response.json().items() if k == "fulfillment_status"} == shown
    await _unchanged(db_engine, order, before)
    assert await _alerts(db_engine, order.order_id) == 1


async def _short_of_its_lines(db: AsyncSession, user_id: uuid.UUID) -> PhysicalOrder:
    """A refund row with no items: the payment's balance drops and the line's does not, so the
    real L4 check refuses the cancel's refund while the totals (Q-2) still agree."""
    order = await seed_physical_order(
        db, user_id=user_id, payment_method="online", payment_status="paid"
    )
    await db.execute(
        text(
            "INSERT INTO refunds (order_id, payment_id, payment_provider, kind, amount_cents,"
            " reason, requested_by, initiated_at)"
            " SELECT order_id, id, provider, 'admin', 1, 'drift', :u, now() FROM payments"
            " WHERE order_id = :o"
        ),
        {"o": order.order_id, "u": user_id},
    )
    await db.commit()
    return order


async def _over_balance_alerts_on_its_payment(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    return await count(
        engine,
        "SELECT count(*) FROM audit_logs a JOIN payments p ON a.entity_id = p.id"
        " WHERE a.action = 'payment.alert_raised' AND a.after_data->>'kind' = 'refund_integrity'"
        " AND a.after_data->>'reason' = 'refund_exceeds_available' AND p.order_id = :o",
        o=order_id,
    )


@pytest.mark.parametrize("route", ["customer", "admin_order", "transition"])
async def test_a_refused_refund_alerts_once_per_payment_not_once_for_all_orders(
    route: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """One order's alert never silences another's: the second order still alerts, while a
    repeat on the first folds into its alert for the window."""
    buyer = await create_user(db_session)
    first = await _short_of_its_lines(db_session, buyer.id)
    second = await _short_of_its_lines(db_session, buyer.id)
    refused = (first, first, second)

    def by_customer(order_id: uuid.UUID) -> Any:
        return as_customer(buyer.email, lambda client: customer_cancel(client, order_id))

    if route == "customer":
        responses = [by_customer(o.order_id) for o in refused]
        assert {r.json()["code"] for r in responses} == {"ORDER_NOT_CANCELLABLE"}
    else:
        with client_for(main_app) as client:
            await mfa_admin(client, db_session)
            if route == "admin_order":
                responses = [admin_cancel(client, o.order_id) for o in refused]
            else:
                responses = [move(client, o, "cancelled") for o in refused]
        assert {r.json()["reason"] for r in responses} == {"refund_exceeds_available"}
    assert {r.status_code for r in responses} == {409}
    for order_id in (first.order_id, second.order_id):
        assert await _alerts(db_engine, order_id) == 1
        assert await _over_balance_alerts_on_its_payment(db_engine, order_id) == 1


async def test_the_forward_writer_never_cancels_a_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """`-> cancelled` goes through `cancel_lines` and its refund; the forward writer refuses
    it even with a legal edge, so a refactor cannot cancel a paid line bare (ADR-043 d1)."""
    order = await seed_physical_order(db_session, payment_method="online", payment_status="paid")
    admin = await create_user(db_session)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        locked = await lock_order_for_change(session, order.order_id)
        assert locked is not None
        with pytest.raises(InvalidLineTransitionError) as caught:
            await transition_physical_line(
                session,
                locked,
                line_id=order.line_ids[0],
                target=OrderItemStatus.CANCELLED,
                admin_id=admin.id,
                at=locked.order.placed_at,
                reached_paid=True,
                refunds=NO_REFUNDS,
                note=None,
            )
    assert caught.value.reason == "not_a_legal_edge"
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])


async def test_the_cancel_writer_refuses_a_line_not_in_the_state_decided_on(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """`cancel_lines` moves a line only from the state the cancel was decided on (A-04)."""
    order = await seed_physical_order(db_session, payment_method="online", payment_status="paid")
    admin = await create_user(db_session)
    stale = LineCancel(order.line_ids[0], OrderItemStatus.IN_PRODUCTION, None)  # it is pending
    async with async_sessionmaker(db_engine)() as session, session.begin():
        locked = await lock_order_for_change(session, order.order_id)
        assert locked is not None
        with pytest.raises(InvalidLineTransitionError) as caught:
            await cancel_lines(
                session,
                locked,
                (stale,),
                actor_user_id=admin.id,
                at=locked.order.placed_at,
                note=None,
                by_customer=False,
            )
    assert caught.value.reason == "not_a_legal_edge"
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])


async def test_a_customer_cancel_after_an_admin_refusal_completes_the_block(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """BR-144 reads every line: the administrator refused one, the customer cancels the
    other (no reason), so the order ends wholly refused and cash is blocked."""
    buyer = await create_user(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, line_states=["ready_to_ship", "pending"]
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refused = move(client, order, "cancelled", line=0, cancel_reason="refused")
        assert refused.status_code == 200, refused.text

    def cancel(client: TestClient) -> Any:
        return customer_cancel(client, order.order_id)

    response = as_customer(buyer.email, cancel)
    assert response.status_code == 200, response.text
    [block] = await blocks_of(db_engine, order.order_id)
    assert block.reason == "refused"
