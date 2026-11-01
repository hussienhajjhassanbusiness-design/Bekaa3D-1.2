"""VS-030 PR C over HTTP: recording chargebacks (plan 2.5, 6.2 I17-I19, I23-I24; owner
answers C1, C4). Absorbed refunds keep every line's coverage; D4 cancels an emptied
unfinished line; a late-captured attempt's chargeback moves no status."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import assert_problem, client_for, login, mfa_admin
from tests.integration.fulfillment.order_support import PhysicalOrder, move, seed_physical_order
from tests.integration.payments.refund_support import (
    ADMIN,
    REFUNDS,
    act,
    audit_rows,
    chargeback,
    count,
    create,
    key,
    late_capture,
    late_refunds,
    line_state,
    ok,
    paid_cash,
    paid_online,
    payment_of,
    queue_ids,
    refund_rows,
    statuses,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

CHARGEBACKS = "SELECT count(*) FROM chargebacks WHERE order_id = :o"


async def _admin(client: TestClient, db: AsyncSession) -> uuid.UUID:
    return (await mfa_admin(client, db))[0].id


async def test_i17_a_pending_goodwill_refund_is_absorbed_and_payout_stays_within_paid(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        admin = await _admin(client, db_session)
        goodwill = ok(create(client, order.order_id, [(line, 200)]), 201)["id"]
        body = ok(chargeback(client, order.order_id, payment, 1000, [(line, 800)]), 201)
        assert (body["applied_cents"], body["excess_cents"]) == (1000, 0)
        assert body["items"][0]["amount_cents"] == 1000  # 200 absorbed + 800 named
        assert goodwill not in queue_ids(client, order.order_id)
        assert body["id"] not in queue_ids(client, order.order_id)  # never an obligation
        voided = ok(client.get(f"{REFUNDS}/{goodwill}"))
    assert voided["status"] == "voided"
    assert voided["void_reason"] == f"absorbed by chargeback {body['id']}"
    assert await line_state(db_engine, line) == "refunded"
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
    (audit,) = await audit_rows(db_engine, "chargeback.recorded", body["id"])
    assert (audit.actor_user_id, audit.entity_type, audit.before_data) == (
        admin,
        "chargeback",
        None,
    )
    assert audit.after_data == {
        "order_id": str(order.order_id),
        "payment_id": str(payment),
        "charged_cents": 1000,
        "applied_cents": 1000,
        "excess_cents": 0,
        "items": [{"order_item_id": str(line), "amount_cents": 1000}],
        "voided_refund_ids": [goodwill],
        "remainder_refund_ids": [],
        "lines_refunded": [str(line)],
        "lines_cancelled": [],
        "reason": "Bank dispute: not received.",
    }


async def test_c1_a_partial_charge_on_a_pending_full_refund_leaves_the_rest_owed(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        full = ok(create(client, order.order_id, [(line, 1000)]), 201)["id"]
        assert await line_state(db_engine, line) == "refunded"
        body = ok(chargeback(client, order.order_id, payment, 600), 201)
        assert (body["applied_cents"], body["excess_cents"]) == (600, 0)
        rows = await refund_rows(db_engine, order.order_id)
        rest = [r for r in rows if r.status == "pending"]
        assert [(r.amount_cents, r.reason) for r in rest] == [
            (400, f"remainder after chargeback {body['id']}")
        ]
        assert str(rest[0].id) in queue_ids(client, order.order_id)
        assert full not in queue_ids(client, order.order_id)
    assert await line_state(db_engine, line) == "refunded"
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


async def test_i17_after_a_settled_full_refund_the_whole_charge_is_excess_and_alerted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 1000)]), 201)["id"]
        ok(act(client, refund, "settle", {}))
        body = ok(chargeback(client, order.order_id, payment, 1000), 201)
    assert (body["applied_cents"], body["excess_cents"]) == (0, 1000)
    alerts = (
        "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
        " AND after_data->>'kind' = 'chargeback_excess' AND after_data->>'chargeback_id' = :c"
    )
    assert await count(db_engine, alerts, c=body["id"]) == 1


async def test_a_chargeback_on_a_drifted_order_writes_nothing_and_alerts(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-042 d18: Q-2 guards the balances a paid chargeback derives (audit A-03)."""
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        goodwill = ok(create(client, order.order_id, [(line, 200)]), 201)["id"]
        await db_session.execute(
            text(
                "UPDATE orders SET subtotal_cents = subtotal_cents + 1,"
                " total_cents = total_cents + 1 WHERE id = :o"
            ),
            {"o": order.order_id},
        )
        await db_session.commit()
        idem = key()
        response = chargeback(
            client, order.order_id, payment, 1000, [(line, 800)], idempotency_key=idem
        )
        assert_problem(response, 409, "ORDER_TOTAL_MISMATCH")
        assert goodwill in queue_ids(client, order.order_id)  # nothing absorbed
    assert await count(db_engine, CHARGEBACKS, o=order.order_id) == 0
    assert [r.status for r in await refund_rows(db_engine, order.order_id)] == ["pending"]
    claims = "SELECT count(*) FROM idempotency_records WHERE key = :k"
    assert await count(db_engine, claims, k=idem) == 0
    alerts = (
        "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
        " AND after_data->>'kind' = 'refund_integrity' AND after_data->>'order_id' = :o"
    )
    assert await count(db_engine, alerts, o=str(order.order_id)) == 1
    assert await statuses(db_engine, order.order_id) == ("partially_refunded", "partially_refunded")


async def test_two_chargebacks_on_one_payment_each_alert(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        first = ok(chargeback(client, order.order_id, payment, 300, [(line, 300)]), 201)
        second = ok(chargeback(client, order.order_id, payment, 300, [(line, 300)]), 201)
    alerts = (
        "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
        " AND after_data->>'kind' = 'chargeback' AND after_data->>'payment_id' = :p"
    )
    assert await count(db_engine, alerts, p=str(payment)) == 2
    assert first["id"] != second["id"]
    assert await statuses(db_engine, order.order_id) == (
        "partially_refunded",
        "partially_refunded",
    )


async def test_i17_i23_i24_refusals_write_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    cash = await paid_cash(db_session)
    cash_payment = await payment_of(db_engine, cash.order_id)
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    line = order.physical[0]
    idem = key()
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(
            chargeback(client, cash.order_id, cash_payment, 500), 422, "CHARGEBACK_NOT_ONLINE"
        )
        first = chargeback(
            client,
            order.order_id,
            payment,
            300,
            [(line, 300)],
            dispute="dp-1",
            idempotency_key=idem,
        )
        assert first.status_code == 201, first.text
        replay = chargeback(
            client,
            order.order_id,
            payment,
            300,
            [(line, 300)],
            dispute="dp-1",
            idempotency_key=idem,
        )
        assert replay.json() == first.json() and replay.headers["Idempotent-Replayed"] == "true"
        assert_problem(
            chargeback(client, order.order_id, payment, 300, [(line, 300)], dispute="dp-1"),
            409,
            "CHARGEBACK_DUPLICATE",
        )
        assert_problem(
            chargeback(
                client,
                order.order_id,
                payment,
                301,
                [(line, 300)],
                dispute="dp-1",
                idempotency_key=idem,
            ),
            409,
            "IDEMPOTENCY_KEY_CONFLICT",
        )
        over = chargeback(client, order.order_id, payment, 2000, [(line, 701)])
        assert_problem(over, 422, "CHARGEBACK_ALLOCATION_INVALID")
        assert over.json()["available"]["payment_cents"] == 700
        assert_problem(chargeback(client, order.order_id, uuid.uuid4(), 100), 404)
        other = await paid_online(db_session, stl=None)
        assert_problem(chargeback(client, other.order_id, payment, 100), 404)
    assert await count(db_engine, CHARGEBACKS, o=cash.order_id) == 0
    assert await count(db_engine, CHARGEBACKS, o=order.order_id) == 1


async def test_a_refund_after_a_chargeback_sees_the_smaller_balance(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(chargeback(client, order.order_id, payment, 600, [(line, 600)]), 201)
        refused = create(client, order.order_id, [(line, 401)])
        assert_problem(refused, 422, "REFUND_EXCEEDS_AVAILABLE")
        assert refused.json()["available"]["payment_cents"] == 400
        ok(create(client, order.order_id, [(line, 400)]), 201)
        detail = ok(client.get(f"{ADMIN}/orders/{order.order_id}"))
    assert [(c["applied_cents"], c["excess_cents"]) for c in detail["chargebacks"]] == [(600, 0)]
    assert detail["refund_balance"]["payment_cents"] == 0
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


async def test_i18_d4_an_emptied_unfinished_line_is_cancelled_and_closed(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(
        db_session, stl=None, physical=("in_production", "returned", "shipped")
    )
    making, returned, shipped = order.physical
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        body = ok(
            chargeback(
                client,
                order.order_id,
                payment,
                3000,
                [(making, 1000), (returned, 1000), (shipped, 1000)],
            ),
            201,
        )
        seeded = PhysicalOrder(order.order_id, order.user_id, "", order.physical, order.phone)
        refused = move(client, seeded, "ready_to_ship")
    assert (body["applied_cents"], body["excess_cents"]) == (3000, 0)
    assert_problem(refused, 409)
    assert refused.json()["reason"] == "line_closed"
    assert [await line_state(db_engine, i) for i in order.physical] == [
        "cancelled",
        "refunded",
        "cancelled",
    ]
    assert await refund_rows(db_engine, order.order_id) == []  # no refund is created
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


async def test_i19_a_late_captured_attempt_absorbs_its_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="expired")
    payment = await payment_of(db_engine, order.order_id)
    await late_capture(db_engine, payment, 1200)
    (late,) = await late_refunds(db_engine, payment)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(
            chargeback(client, order.order_id, payment, 500, [(order.line_ids[0], 500)]),
            422,
            "CHARGEBACK_ITEMS_FORBIDDEN",
        )
        body = ok(chargeback(client, order.order_id, payment, 500), 201)
    assert (body["applied_cents"], body["excess_cents"], body["items"]) == (500, 0, [])
    rows = await late_refunds(db_engine, payment)
    assert [(r.status, r.amount_cents) for r in rows] == [("voided", 1200), ("pending", 700)]
    assert rows[0].id == late.id
    async with db_engine.connect() as conn:
        order_status = await conn.scalar(
            text("SELECT status::text FROM orders WHERE id = :o"), {"o": order.order_id}
        )
    assert order_status == "pending_payment"


async def test_an_attempt_that_never_took_money_cannot_be_charged_back(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="expired")
    payment = await payment_of(db_engine, order.order_id)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(chargeback(client, order.order_id, payment, 100), 409, "ORDER_NOT_PAID")


async def test_the_customer_never_sees_a_chargeback(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    email = await db_session.scalar(
        text("SELECT email FROM users WHERE id = :u"), {"u": order.user_id}
    )
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.physical[0], 200)]), 201)
        cb = ok(chargeback(client, order.order_id, payment, 100), 201)
        assert ok(client.get(f"{ADMIN}/chargebacks/{cb['id']}"))["id"] == cb["id"]
        listed = client.get(f"{ADMIN}/orders/{order.order_id}/chargebacks")
        assert listed.status_code == 200, listed.text
        assert [c["id"] for c in listed.json()] == [cb["id"]]
        assert_problem(client.get(f"{ADMIN}/chargebacks/{uuid.uuid4()}"), 404)
        assert_problem(client.get(f"{ADMIN}/orders/{uuid.uuid4()}/chargebacks"), 404)
    with client_for(main_app) as customer:
        login(customer, str(email))
        body = ok(customer.get(f"/api/v1/me/orders/{order.order_id}"))
    # The $2 refund was absorbed ($1 charged): the $1 remainder is what the customer sees.
    assert [(r["kind"], r["status"], r["amount"]["amount_cents"]) for r in body["refunds"]] == [
        ("admin", "processing", 100)
    ]
    assert "chargeback" not in str(body)


async def test_an_under_allocated_chargeback_is_refused_so_excess_is_never_refundable(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The PR C review Blocker: excess may only appear once nothing is left to refund."""
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refused = chargeback(client, order.order_id, payment, 1000, [(line, 400)])
        assert_problem(refused, 422, "CHARGEBACK_ALLOCATION_INVALID")
        assert refused.json()["available"]["chargeable_cents"] == 1000
        assert await count(db_engine, CHARGEBACKS, o=order.order_id) == 0
        ok(chargeback(client, order.order_id, payment, 1000, [(line, 1000)]), 201)
        assert_problem(create(client, order.order_id, [(line, 1)]), 422, "REFUND_EXCEEDS_AVAILABLE")
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


async def test_a_late_attempts_owed_obligation_is_absorbed_with_a_remainder(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="expired")
    payment = await payment_of(db_engine, order.order_id)
    await late_capture(db_engine, payment, 1200)
    (late,) = await late_refunds(db_engine, payment)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(act(client, late.id, "fail", {"reason": "Card closed."}))
        body = ok(chargeback(client, order.order_id, payment, 500), 201)
    assert (body["applied_cents"], body["excess_cents"]) == (500, 0)
    rows = await late_refunds(db_engine, payment)
    assert [(r.status, r.amount_cents) for r in rows] == [("voided", 1200), ("pending", 700)]


async def test_a_mixed_order_charged_back_in_full_after_a_partial_stl_refund(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Partial STL refund, physical line delivered, the bank takes everything."""
    order = await paid_online(db_session, physical=("delivered",))  # 1000 + STL 500
    assert order.stl is not None
    payment = await payment_of(db_engine, order.order_id)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        partial = ok(create(client, order.order_id, [(order.stl, 200)]), 201)["id"]
        refused = chargeback(client, order.order_id, payment, 1500, [(line, 1000)])
        assert refused.json()["available"]["chargeable_cents"] == 1300
        body = ok(
            chargeback(client, order.order_id, payment, 1500, [(line, 1000), (order.stl, 300)]),
            201,
        )
        assert partial not in queue_ids(client, order.order_id)
    assert (body["applied_cents"], body["excess_cents"]) == (1500, 0)
    assert [await line_state(db_engine, i) for i in (line, order.stl)] == ["refunded", "refunded"]
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
    owned = await db_session.scalar(
        text(
            "SELECT count(*) FROM order_items WHERE id = :i"
            " AND fulfillment_status = 'awaiting_delivery'"
        ),
        {"i": order.stl},
    )
    assert owned == 0  # out of the delivery queue, ownership freed
