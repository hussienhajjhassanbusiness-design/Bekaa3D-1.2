"""VS-030 end to end (plan 6.6 E1): a paid mixed order is refunded in two parts over HTTP.
The first is settled; the second fails, is reissued and settled. The queue empties, both
the order and the payment read refunded, and the customer sees two refunded refunds."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import client_for, login, mfa_admin
from tests.integration.payments.refund_support import (
    act,
    create,
    ok,
    paid_online,
    queue_ids,
    statuses,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def test_a_mixed_order_is_refunded_settled_failed_reissued_and_settled(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session)
    assert order.stl is not None
    email = await db_session.scalar(
        text("SELECT email FROM users WHERE id = :u"), {"u": order.user_id}
    )
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        first = ok(create(admin, order.order_id, [(order.stl, 500)]), 201)
        assert queue_ids(admin, order.order_id) == {first["id"]}
        ok(act(admin, first["id"], "settle", {"reference": "dash-1"}))
        assert await statuses(db_engine, order.order_id) == (
            "partially_refunded",
            "partially_refunded",
        )
        second = ok(create(admin, order.order_id, [(order.physical[0], 1000)]), 201)
        assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
        ok(act(admin, second["id"], "fail", {"reason": "The card was closed."}))
        assert queue_ids(admin, order.order_id) == {second["id"]}
        assert await statuses(db_engine, order.order_id) == (
            "partially_refunded",
            "partially_refunded",
        )
        twin = ok(act(admin, second["id"], "reissue"), 201)
        ok(act(admin, twin["id"], "settle", {"reference": "dash-2"}))
        assert queue_ids(admin, order.order_id) == set()
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
    with client_for(main_app) as customer:
        login(customer, str(email))
        body = ok(customer.get(f"/api/v1/me/orders/{order.order_id}"))
    assert body["status"] == "refunded"
    assert [(r["status"], r["amount"]["amount_cents"]) for r in body["refunds"]] == [
        ("refunded", 500),
        ("refunded", 1000),
    ]
