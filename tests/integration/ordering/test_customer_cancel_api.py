"""VS-031 over HTTP: `POST /api/v1/me/orders/{id}/cancel` (FR-09, F-033; SRS 8.9; ADR-033
d4, ADR-043). Every refusal asserts that nothing changed."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.fulfillment.public import cancel_order_by_customer
from app.main import app as main_app
from app.ordering.public import LineNotFoundError
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.cancel_support import (
    as_customer,
    cancel_audits,
    cancel_history,
    customer_cancel,
    customer_cancel_path,
    customer_cancelled_at,
    refunds_of,
)
from tests.integration.fulfillment.delivery_support import seed_stl_order
from tests.integration.fulfillment.order_support import (
    effects,
    emails,
    notifications,
    seed_physical_order,
    states,
)
from tests.integration.payments.refund_support import create, line_state, statuses

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _buyer(db: AsyncSession) -> Any:
    return await create_user(db)


def _detail(client: TestClient, order_id: uuid.UUID) -> dict[str, Any]:
    response = client.get(f"/api/v1/me/orders/{order_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- what a cancel does ---------------------------------------------------------------------


async def test_a_paid_physical_order_is_cancelled_and_refunded_in_full(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=buyer.id,
        email=buyer.email,
        payment_method="online",
        payment_status="paid",
        line_states=["pending", "pending"],
    )

    def cancel(client: TestClient) -> Any:
        return customer_cancel(client, order.order_id, "  Changed my mind  ")

    response = as_customer(buyer.email, cancel)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["can_cancel"]) == ("cancelled", False)
    assert [r["status"] for r in body["refunds"]] == ["processing"]
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
    [refund] = await refunds_of(db_engine, order.order_id)
    assert (refund.kind, refund.status, refund.amount_cents) == ("cancellation", "pending", 2000)
    assert (refund.requested_by, refund.approved_by) == (buyer.id, None)
    assert refund.items == {str(i): 1000 for i in order.line_ids}
    assert await customer_cancelled_at(db_engine, order.order_id) is not None
    [audit] = await cancel_audits(db_engine, order.order_id)
    assert audit.actor_user_id == buyer.id
    assert (audit.after_data["by"], audit.after_data["refund_cents"]) == ("customer", 2000)
    assert audit.after_data["has_note"] is True and "note" not in audit.after_data
    assert await cancel_history(db_engine, order.order_id) == {
        (line, "pending", buyer.id, "Changed my mind") for line in order.line_ids
    }
    shown = {
        (h["order_item_id"], h["from_status"])
        for h in body["status_history"]
        if h["to_status"] == "cancelled" and h["order_item_id"] is not None
    }
    assert shown == {(str(line), "pending") for line in order.line_ids}
    templates = [m[0] for m in await emails(db_engine, order.order_id)]
    assert sorted(templates) == ["order_cancelled", "order_refund_issued"]
    assert sorted(await notifications(db_engine, order.order_id)) == [
        "order.cancelled",
        "refund.issued",
    ]


async def test_a_paid_mixed_order_cancels_only_its_physical_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=buyer.id,
        payment_method="online",
        payment_status="paid",
        stl_line="awaiting_delivery",
    )
    response = as_customer(buyer.email, lambda c: customer_cancel(c, order.order_id))
    assert response.status_code == 200, response.text
    assert await statuses(db_engine, order.order_id) == (
        "partially_refunded",
        "partially_refunded",
    )
    stl = next(line for line in response.json()["lines"] if line["product_type"] == "stl")
    assert stl["fulfillment_status"] == "awaiting_delivery"
    [refund] = await refunds_of(db_engine, order.order_id)
    assert refund.items == {str(order.line_ids[0]): 1000}


async def test_an_unpaid_cash_order_is_cancelled_with_no_refund(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id, line_states=["pending"])
    response = as_customer(buyer.email, lambda c: customer_cancel(c, order.order_id))
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["payment_due"]) == ("cancelled", False)
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled"])
    assert await refunds_of(db_engine, order.order_id) == []
    assert await customer_cancelled_at(db_engine, order.order_id) is not None
    [(template, payload)] = await emails(db_engine, order.order_id)
    assert template == "order_cancelled"
    assert (payload["order_cancelled"], payload["amount_due_cents"]) == (True, None)
    assert not any("phone" in key for key in payload)


async def test_a_line_the_admin_already_cancelled_is_ignored(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-033 d4: it neither blocks the cancel nor counts as the physical line it needs."""
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, line_states=["cancelled", "pending"]
    )

    def detail_then_cancel(client: TestClient) -> tuple[bool, Any]:
        return _detail(client, order.order_id)["can_cancel"], customer_cancel(
            client, order.order_id
        )

    flag, response = as_customer(buyer.email, detail_then_cancel)
    assert flag is True and response.status_code == 200, response.text
    assert await states(db_engine, order.order_id) == ("cancelled", ["cancelled", "cancelled"])


async def test_a_goodwill_refund_then_a_self_cancel_refunds_exactly_the_rest(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, payment_method="online", payment_status="paid"
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert create(client, order.order_id, [(order.line_ids[0], 300)]).status_code == 201
    response = as_customer(buyer.email, lambda c: customer_cancel(c, order.order_id))
    assert response.status_code == 200, response.text
    goodwill, cancellation = await refunds_of(db_engine, order.order_id)
    assert (goodwill.kind, goodwill.amount_cents) == ("admin", 300)
    assert (cancellation.kind, cancellation.amount_cents) == ("cancellation", 700)
    assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")


# --- refusals change nothing ---------------------------------------------------------------


@pytest.mark.parametrize(
    "seed",
    [
        {"payment_method": "online", "payment_status": None},
        {"payment_method": "online", "payment_status": "pending"},
        {"line_states": ["in_production"]},
        {"line_states": ["pending", "in_production"]},
        {"line_states": ["ready_to_ship"]},
        {"line_states": ["cancelled"], "order_status": "cancelled"},
    ],
    ids=["unpaid_online", "pending_payment", "printing", "one_printing", "ready", "cancelled"],
)
async def test_a_cancel_that_cannot_occur_is_a_409_and_changes_nothing(
    seed: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(db_session, user_id=buyer.id, **seed)
    before = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))

    def check(client: TestClient) -> tuple[bool, Any]:
        return _detail(client, order.order_id)["can_cancel"], customer_cancel(
            client, order.order_id
        )

    flag, response = as_customer(buyer.email, check)
    assert flag is False
    assert_problem(response, 409, "ORDER_NOT_CANCELLABLE")
    after = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))
    assert after == before
    assert await refunds_of(db_engine, order.order_id) == []


async def test_an_stl_only_order_is_never_self_cancelled(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    seeded, stl = await seed_stl_order(db_session, user_id=buyer.id)
    order_id = seeded.order_id

    def check(client: TestClient) -> tuple[bool, Any]:
        return _detail(client, order_id)["can_cancel"], customer_cancel(client, order_id)

    flag, response = as_customer(buyer.email, check)
    assert flag is False
    assert_problem(response, 409, "ORDER_NOT_CANCELLABLE")
    assert await line_state(db_engine, stl) == "awaiting_delivery"


async def test_a_second_cancel_is_a_409_and_refunds_nothing_twice(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, payment_method="online", payment_status="paid"
    )

    def twice(client: TestClient) -> tuple[Any, Any]:
        return customer_cancel(client, order.order_id), customer_cancel(client, order.order_id)

    first, second = as_customer(buyer.email, twice)
    assert first.status_code == 200, first.text
    assert_problem(second, 409, "ORDER_NOT_CANCELLABLE")
    assert len(await refunds_of(db_engine, order.order_id)) == 1


async def test_another_customers_order_is_a_404_and_unchanged(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    owner, other = await _buyer(db_session), await _buyer(db_session)
    order = await seed_physical_order(db_session, user_id=owner.id)

    def both(client: TestClient) -> list[Any]:
        return [customer_cancel(client, o) for o in (order.order_id, uuid.uuid4())]

    for response in as_customer(other.email, both):
        assert_problem(response, 404, "NOT_FOUND")
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])


async def test_the_use_case_refuses_another_customers_order_by_itself(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The ownership check, not the route's later 404 read, stops a foreign cancel (A-01)."""
    owner, other = await _buyer(db_session), await _buyer(db_session)
    order = await seed_physical_order(
        db_session, user_id=owner.id, payment_method="online", payment_status="paid"
    )
    before = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))
    with pytest.raises(LineNotFoundError):
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await cancel_order_by_customer(
                session,
                order_id=order.order_id,
                user_id=other.id,
                at=datetime.now(UTC),
                note=None,
                request_id=None,
                ip_hash=None,
            )
    after = (await states(db_engine, order.order_id), await effects(db_engine, order.order_id))
    assert after == before
    assert await refunds_of(db_engine, order.order_id) == []
    assert await customer_cancelled_at(db_engine, order.order_id) is None


async def test_csrf_and_a_verified_email_are_required(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer, unverified = await _buyer(db_session), await create_user(db_session, verified=False)
    order = await seed_physical_order(db_session, user_id=buyer.id)
    mine = await seed_physical_order(db_session, user_id=unverified.id)
    no_csrf = as_customer(
        buyer.email, lambda c: c.post(customer_cancel_path(order.order_id), json={})
    )
    assert_problem(no_csrf, 403, "CSRF_INVALID")
    blocked = as_customer(unverified.email, lambda c: customer_cancel(c, mine.order_id))
    assert_problem(blocked, 403, "EMAIL_VERIFICATION_REQUIRED")
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])
    assert await states(db_engine, mine.order_id) == ("in_progress", ["pending"])


async def test_an_overlong_reason_is_a_422_and_the_limit_is_ten_an_hour(
    db_session: AsyncSession,
) -> None:
    buyer = await _buyer(db_session)

    def spam(client: TestClient) -> list[int]:
        long = customer_cancel(client, uuid.uuid4(), "x" * 501).status_code
        return [long] + [customer_cancel(client, uuid.uuid4()).status_code for _ in range(10)]

    codes = as_customer(buyer.email, spam)
    assert codes[0] == 422
    assert codes[1:10] == [404] * 9 and codes[10] == 429


async def test_a_failing_refund_rolls_the_whole_cancel_back(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-09: cancellation and the refund obligation are atomic."""
    buyer = await _buyer(db_session)
    order = await seed_physical_order(
        db_session, user_id=buyer.id, payment_method="online", payment_status="paid"
    )

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("refund store down")

    monkeypatch.setattr(
        "app.payments.infrastructure.refunds.SqlRefundStore.insert", boom, raising=True
    )
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, buyer.email)
        response = customer_cancel(client, order.order_id)
    assert response.status_code == 500
    assert await states(db_engine, order.order_id) == ("in_progress", ["pending"])
    assert await refunds_of(db_engine, order.order_id) == []
    assert await customer_cancelled_at(db_engine, order.order_id) is None
    async with db_engine.connect() as conn:
        audits = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE entity_id = :o"), {"o": order.order_id}
        )
    assert audits == 0
