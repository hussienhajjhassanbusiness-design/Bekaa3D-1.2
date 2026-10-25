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

    def over(*args: Any, **kwargs: Any) -> None:
        raise RefundExceedsAvailableError(lines={}, payment_cents=0)

    monkeypatch.setattr("app.payments.application.services.refunds.check_request", over)
    before = await effects(db_engine, order.order_id)
    with client_for(main_app) as client:
        login(client, buyer.email)
        response = customer_cancel(client, order.order_id)
    assert_problem(response, 409, "ORDER_NOT_CANCELLABLE")
    await _unchanged(db_engine, order, before)
    assert await _alerts(db_engine, order.order_id) == 1


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
