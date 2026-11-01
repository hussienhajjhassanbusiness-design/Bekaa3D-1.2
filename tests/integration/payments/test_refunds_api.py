"""VS-030 PR B over HTTP: refund create, settle, fail, reissue and void (plan 6.2 I1-I5,
I7-I14, I21, I25; 6.5 S2-S3). Orders are seeded paid; no provider is ever called."""

import io
import json
import logging
import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import hash_phone
from app.main import app as main_app
from app.ordering.public import stl_owned
from app.payments.application.ports import PaymentProviderPort
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.order_support import PhysicalOrder, move, seed_physical_order
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    post_checkout,
    shop_open,  # noqa: F401
)
from tests.integration.payments.refund_support import (
    ADMIN,
    REFUNDS,
    act,
    audit_rows,
    count,
    create,
    key,
    line_state,
    ok,
    paid_cash,
    paid_online,
    queue_ids,
    refund_count,
    statuses,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _admin(client: TestClient, db: AsyncSession) -> uuid.UUID:
    return (await mfa_admin(client, db))[0].id


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """`configure_logging()` drops caplog's handler at app start, so its handlers write here."""
    buffer = io.StringIO()
    original = logging.StreamHandler

    def into_buffer(*_args: Any, **_kwargs: Any) -> logging.Handler:
        return original(buffer)

    monkeypatch.setattr(logging, "StreamHandler", into_buffer)
    return buffer


# --- I1, S2 -------------------------------------------------------------------------------


async def test_i1_create_on_a_paid_mixed_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session)
    with client_for(main_app) as client:
        admin = await _admin(client, db_session)
        body = ok(create(client, order.order_id, [(order.physical[0], 300)]), 201)
    assert body["status"] == "pending" and body["kind"] == "admin" and body["amount_cents"] == 300
    assert body["requested_by"] == body["approved_by"] == str(admin)
    assert [(i["order_item_id"], i["amount_cents"]) for i in body["items"]] == [
        (str(order.physical[0]), 300)
    ]
    assert await statuses(db_engine, order.order_id) == ("partially_refunded", "partially_refunded")
    assert await line_state(db_engine, order.physical[0]) == "delivered"
    refund = body["id"]
    assert (
        await count(
            db_engine,
            "SELECT count(*) FROM audit_logs WHERE action = 'refund.created' AND entity_id = :r",
            r=uuid.UUID(refund),
        )
        == 1
    )
    assert (
        await count(
            db_engine,
            "SELECT count(*) FROM email_outbox WHERE template = 'order_refund_issued'"
            " AND payload->>'refund_id' = :r",
            r=refund,
        )
        == 1
    )
    assert (
        await count(
            db_engine,
            "SELECT count(*) FROM notifications WHERE type = 'refund'"
            " AND payload->>'refund_id' = :r",
            r=refund,
        )
        == 1
    )
    # S2: no phone, hash, address or provider reference anywhere the refund wrote.
    async with db_engine.connect() as conn:
        stored = json.dumps(
            [
                body,
                *(
                    await conn.execute(
                        text(
                            "SELECT before_data, after_data FROM audit_logs WHERE entity_id = :r"
                            " UNION ALL SELECT payload, NULL FROM email_outbox"
                            " WHERE payload->>'refund_id' = CAST(:r AS text)"
                            " UNION ALL SELECT payload, NULL FROM notifications"
                            " WHERE payload->>'refund_id' = CAST(:r AS text)"
                        ),
                        {"r": uuid.UUID(refund)},
                    )
                ).all(),
            ],
            default=str,
        )
        reference = await conn.scalar(
            text("SELECT provider_payment_id FROM payments WHERE order_id = :o"),
            {"o": order.order_id},
        )
    for secret in (order.phone, hash_phone(order.phone), str(reference), "Zahle", "Blue door"):
        assert secret not in stored


# --- I2 -----------------------------------------------------------------------------------


async def test_i2_partial_then_rest_on_a_delivered_line_and_an_awaiting_stl(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session)
    assert order.stl is not None
    product = await db_session.scalar(
        text("SELECT product_id FROM order_items WHERE id = :i"), {"i": order.stl}
    )
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.physical[0], 400), (order.stl, 200)]), 201)
        assert await line_state(db_engine, order.physical[0]) == "delivered"
        assert await line_state(db_engine, order.stl) == "awaiting_delivery"
        assert await stl_owned(db_session, user_id=order.user_id, product_id=product)
        ok(create(client, order.order_id, [(order.physical[0], 600), (order.stl, 300)]), 201)
    assert await line_state(db_engine, order.physical[0]) == "refunded"
    assert await line_state(db_engine, order.stl) == "refunded"
    await db_session.rollback()
    assert not await stl_owned(db_session, user_id=order.user_id, product_id=product)
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


@pytest.mark.usefixtures("shop_open")
async def test_a_customer_whose_stl_line_was_refunded_in_full_can_buy_it_again(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session)
    assert order.stl is not None
    product, email = (
        await db_session.execute(
            text(
                "SELECT i.product_id, u.email FROM order_items i JOIN users u ON u.id = i.user_id"
                " WHERE i.id = :i"
            ),
            {"i": order.stl},
        )
    ).one()
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 500)]), 201)
    assert await line_state(db_engine, order.stl) == "refunded"
    with client_for(main_app) as customer:
        login(customer, email)
        add_to_cart(customer, product)  # the cart's ownership check lets it in
        response = post_checkout(customer)  # and the ownership index lets the new line in
    assert response.status_code == 201, response.text
    [line] = response.json()["order"]["lines"]
    assert (line["product_id"], line["fulfillment_status"]) == (str(product), "pending")


# --- I3, I4, I5 ----------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["online", "cash"])
async def test_i3_an_unpaid_order_is_not_refundable(
    method: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method=method, payment_status="pending" if method == "online" else None
    )
    with client_for(main_app) as client:
        await _admin(client, db_session)
        response = create(client, order.order_id, [(order.line_ids[0], 100)])
    assert_problem(response, 409, "ORDER_NOT_PAID")
    assert await refund_count(db_engine, order.order_id) == 0


async def test_i4_cash_is_capped_at_the_cash_recorded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_cash(db_session, lines=("delivered", "cancelled"))
    live, cancelled = order.physical
    with client_for(main_app) as client:
        await _admin(client, db_session)
        over = create(client, order.order_id, [(live, 1001)])
        assert_problem(over, 422, "REFUND_EXCEEDS_AVAILABLE")
        assert over.json()["available"]["payment_cents"] == 1000
        assert_problem(
            create(client, order.order_id, [(cancelled, 1)]), 422, "REFUND_EXCEEDS_AVAILABLE"
        )
        ok(create(client, order.order_id, [(live, 1000)]), 201)
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


async def test_i4_a_cash_payment_below_its_lines_caps_the_sum(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_cash(db_session, lines=("delivered", "delivered"), recorded_cents=1500)
    a, b = order.physical
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(
            create(client, order.order_id, [(a, 1000), (b, 501)]), 422, "REFUND_EXCEEDS_AVAILABLE"
        )
        ok(create(client, order.order_id, [(a, 1000), (b, 500)]), 201)


async def test_i5_an_order_total_mismatch_writes_nothing_and_alerts(
    db_engine: AsyncEngine, db_session: AsyncSession, app_logs: io.StringIO
) -> None:
    order = await paid_online(db_session, stl=None)
    await db_session.execute(
        text(
            "UPDATE orders SET subtotal_cents = subtotal_cents + 1,"
            " total_cents = total_cents + 1 WHERE id = :o"
        ),
        {"o": order.order_id},
    )
    await db_session.commit()
    idem = key()
    with client_for(main_app) as client:
        await _admin(client, db_session)
        response = create(client, order.order_id, [(order.physical[0], 100)], idempotency_key=idem)
    assert_problem(response, 409, "ORDER_TOTAL_MISMATCH")
    assert await refund_count(db_engine, order.order_id) == 0
    assert (
        await count(db_engine, "SELECT count(*) FROM idempotency_records WHERE key = :k", k=idem)
        == 0
    )
    assert (
        await count(
            db_engine,
            "SELECT count(*) FROM audit_logs WHERE action = 'payment.alert_raised'"
            " AND after_data->>'kind' = 'refund_integrity' AND after_data->>'order_id' = :o",
            o=str(order.order_id),
        )
        == 1
    )
    assert await statuses(db_engine, order.order_id) == ("in_progress", "paid")
    logged = [
        re.sub(r"\x1b\[[0-9;]*m", "", entry)  # the dev console renderer colours its output
        for entry in app_logs.getvalue().splitlines()
        if "refund_integrity_error" in entry
    ]
    assert len(logged) == 1, app_logs.getvalue() or "log capture is not working"
    assert "[error" in logged[0] and str(order.order_id) in logged[0]


# --- I7 -----------------------------------------------------------------------------------


async def test_i7_idempotency(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    idem = key()
    with client_for(main_app) as client:
        await _admin(client, db_session)
        first = create(client, order.order_id, [(a, 100)], idempotency_key=idem)
        again = create(client, order.order_id, [(a, 100)], idempotency_key=idem)
        assert again.status_code == 201 and again.json() == first.json()
        assert again.headers["Idempotent-Replayed"] == "true"
        other = create(client, order.order_id, [(a, 101)], idempotency_key=idem)
        assert_problem(other, 409, "IDEMPOTENCY_KEY_CONFLICT")
        assert await refund_count(db_engine, order.order_id) == 1
        retry = key()
        assert_problem(create(client, order.order_id, [(b, 5000)], idempotency_key=retry), 422)
        ok(create(client, order.order_id, [(b, 500)], idempotency_key=retry), 201)
    assert await refund_count(db_engine, order.order_id) == 2


async def test_create_and_reissue_require_an_idempotency_key(
    db_session: AsyncSession,
) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        response = client.post(
            f"{ADMIN}/orders/{order.order_id}/refunds",
            json={
                "items": [{"order_item_id": str(order.physical[0]), "amount_cents": 1}],
                "reason": "x",
            },
            headers=csrf(client),
        )
        assert_problem(response, 422, "VALIDATION_ERROR")
        refund = ok(create(client, order.order_id, [(order.physical[0], 1)]), 201)["id"]
        ok(act(client, refund, "fail", {"reason": "Bounced."}))
        bare = client.post(f"{REFUNDS}/{refund}/reissue", headers=csrf(client))
        assert_problem(bare, 422, "VALIDATION_ERROR")


# --- I8, I9, I10 --------------------------------------------------------------------------


async def test_i8_settle_changes_no_status_and_repeats(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        admin = await _admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 1000)]), 201)["id"]
        before = await statuses(db_engine, order.order_id)
        settled = ok(act(client, refund, "settle", {"reference": "dash-123"}))
        assert settled["status"] == "settled" and settled["settlement_reference"] == "dash-123"
        assert await statuses(db_engine, order.order_id) == before == ("refunded", "refunded")
        assert ok(act(client, refund, "settle", {})) == settled
        (audit,) = await audit_rows(db_engine, "refund.settled", refund)  # the replay writes none
        assert (audit.actor_user_id, audit.entity_type) == (admin, "refund")
        assert audit.before_data == {"status": "pending"}
        assert audit.after_data == {
            "status": "settled",
            "order_id": str(order.order_id),
            "amount_cents": 1000,
        }
        assert refund not in queue_ids(client, order.order_id)
        other = await paid_online(db_session, stl=None)
        failed = ok(create(client, other.order_id, [(other.physical[0], 10)]), 201)["id"]
        ok(act(client, failed, "fail", {"reason": "Bounced."}))
        assert_problem(act(client, failed, "settle", {}), 409, "INVALID_STATE_TRANSITION")
        voided = ok(create(client, other.order_id, [(other.physical[0], 10)]), 201)["id"]
        ok(act(client, voided, "void", {"reason": "Entered twice."}))
        response = act(client, voided, "settle", {})
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "not_pending"


async def test_i9_a_failed_full_refund_stays_owed_until_reissued(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    with client_for(main_app) as client:
        admin = await _admin(client, db_session)
        refund = ok(create(client, order.order_id, [(line, 1000)]), 201)["id"]
        assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
        failed = ok(act(client, refund, "fail", {"reason": "Card closed."}))
        assert failed["owed"] and refund in queue_ids(client, order.order_id)
        assert await line_state(db_engine, line) == "refunded"
        assert await statuses(db_engine, order.order_id) == (
            "partially_refunded",
            "partially_refunded",
        )
        assert ok(act(client, refund, "fail", {"reason": "again"})) == failed
        assert_problem(create(client, order.order_id, [(line, 1)]), 422, "REFUND_EXCEEDS_AVAILABLE")
        twin = ok(act(client, refund, "reissue"), 201)
        assert twin["reissue_of_refund_id"] == refund and twin["status"] == "pending"
        assert twin["reason"] == f"reissue of {refund}"
        queue = queue_ids(client, order.order_id)
        assert refund not in queue and twin["id"] in queue
        old = ok(client.get(f"{REFUNDS}/{refund}"))
        assert old["reissued_by_refund_id"] == twin["id"] and not old["owed"]
        again = act(client, refund, "reissue")
    assert_problem(again, 409, "INVALID_STATE_TRANSITION")
    assert again.json()["reason"] == "already_reissued"
    assert again.json()["reissued_by_refund_id"] == twin["id"]
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")
    common = {"order_id": str(order.order_id), "amount_cents": 1000}
    (fail_row,) = await audit_rows(db_engine, "refund.failed", refund)  # the replay writes none
    assert (fail_row.actor_user_id, fail_row.entity_type) == (admin, "refund")
    assert fail_row.before_data == {"status": "pending"}
    assert fail_row.after_data == common | {"status": "failed", "reason": "Card closed."}
    (reissue_row,) = await audit_rows(db_engine, "refund.reissued", refund)
    assert (reissue_row.actor_user_id, reissue_row.entity_type) == (admin, "refund")
    assert reissue_row.before_data == {"status": "failed"}
    assert reissue_row.after_data == common | {"reissued_by_refund_id": twin["id"]}


async def test_i10_two_partials_complete_a_line_then_the_first_fails(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        first = ok(create(client, order.order_id, [(line, 400)]), 201)["id"]
        ok(create(client, order.order_id, [(line, 600)]), 201)
        assert await line_state(db_engine, line) == "refunded"
        ok(act(client, first, "fail", {"reason": "Bounced."}))
        assert await line_state(db_engine, line) == "refunded"
        assert (await statuses(db_engine, order.order_id))[0] == "partially_refunded"
        ok(act(client, first, "reissue"), 201)
    assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")


# --- I11, I25 -----------------------------------------------------------------------------


async def test_i11_void_a_pending_partial(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refund = ok(create(client, order.order_id, [(line, 400)]), 201)["id"]
        voided = ok(act(client, refund, "void", {"reason": "Wrong order."}))
        assert voided["status"] == "voided" and refund not in queue_ids(client, order.order_id)
        # Recomputed from the rows: a delivered line and no live refund is a completed order.
        assert await statuses(db_engine, order.order_id) == ("completed", "paid")
        ok(create(client, order.order_id, [(line, 999)]), 201)  # the 400 is free again
        full = await paid_online(db_session, stl=None)
        whole = ok(create(client, full.order_id, [(full.physical[0], 1000)]), 201)["id"]
        refused = act(client, whole, "void", {"reason": "Oops."})
        assert_problem(refused, 409, "INVALID_STATE_TRANSITION")
        assert refused.json()["reason"] == "line_already_refunded"
        ok(act(client, whole, "settle", {}))
        settled = act(client, whole, "void", {"reason": "Oops."})
    assert settled.json()["reason"] == "already_settled"


async def test_i25_void_rules(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    buyer = await create_user(db_session)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        pending = ok(create(client, order.order_id, [(a, 100)]), 201)["id"]
        assert_problem(act(client, pending, "void", {}), 422, "VALIDATION_ERROR")
        assert_problem(act(client, pending, "void", {"reason": ""}), 422, "VALIDATION_ERROR")
        first = ok(act(client, pending, "void", {"reason": "Entered twice."}))
        second = ok(act(client, pending, "void", {"reason": "Another reason."}))
        assert second["void_reason"] == first["void_reason"] == "Entered twice."
        audits = "SELECT count(*) FROM audit_logs WHERE action = 'refund.voided' AND entity_id = :r"
        assert await count(db_engine, audits, r=uuid.UUID(pending)) == 1
        owed = ok(create(client, order.order_id, [(b, 100)]), 201)["id"]
        ok(act(client, owed, "fail", {"reason": "Bounced."}))
        assert owed in queue_ids(client, order.order_id)
        ok(act(client, owed, "void", {"reason": "Customer declined it."}))
        assert owed not in queue_ids(client, order.order_id)
        reissue = act(client, owed, "reissue")
        assert reissue.json()["reason"] == "not_failed"
        assert await refund_count(db_engine, order.order_id) == 2
    with client_for(main_app) as customer:
        login(customer, buyer.email)
        assert_problem(
            customer.post(
                f"{REFUNDS}/{pending}/void", json={"reason": "x"}, headers=csrf(customer)
            ),
            404,
        )
    settled_order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        done = ok(create(client, settled_order.order_id, [(settled_order.physical[0], 10)]), 201)
        ok(act(client, done["id"], "settle", {}))
    with pytest.raises(IntegrityError) as caught:
        async with db_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE refunds SET status = 'voided', voided_at = now(), void_reason = 'x'"
                    " WHERE id = :r"
                ),
                {"r": uuid.UUID(done["id"])},
            )
    assert "ck_refunds_void_never_settled" in str(caught.value)


async def test_a_void_never_strands_the_money_of_a_cancelled_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refund = ok(create(client, order.order_id, [(line, 400)]), 201)["id"]
        # VS-031's cancel writer stands in: the line is cancelled with this refund on it.
        await db_session.execute(
            text(
                "UPDATE order_items SET fulfillment_status = 'cancelled', cancelled_at = now()"
                " WHERE id = :i"
            ),
            {"i": line},
        )
        await db_session.commit()
        refused = act(client, refund, "void", {"reason": "Oops."})
        assert refund in queue_ids(client, order.order_id)  # still owed to the customer
    assert_problem(refused, 409, "INVALID_STATE_TRANSITION")
    assert refused.json()["reason"] == "line_already_cancelled"
    assert await line_state(db_engine, line) == "cancelled"


async def test_settle_records_a_payout_even_when_the_totals_drifted(
    db_session: AsyncSession,
) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    with client_for(main_app) as client:
        await _admin(client, db_session)
        paid_out = ok(create(client, order.order_id, [(a, 100)]), 201)["id"]
        other = ok(create(client, order.order_id, [(b, 100)]), 201)["id"]
        await db_session.execute(
            text(
                "UPDATE orders SET subtotal_cents = subtotal_cents + 1,"
                " total_cents = total_cents + 1 WHERE id = :o"
            ),
            {"o": order.order_id},
        )
        await db_session.commit()
        assert ok(act(client, paid_out, "settle", {}))["status"] == "settled"
        refused = act(client, other, "fail", {"reason": "Bounced."})
    assert_problem(refused, 409, "ORDER_TOTAL_MISMATCH")


# --- I12, I13, I14 ------------------------------------------------------------------------


async def test_i12_mixed_orders(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_online(db_session)
    assert order.stl is not None
    phys = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 500)]), 201)
        assert (await line_state(db_engine, order.stl), await line_state(db_engine, phys)) == (
            "refunded",
            "delivered",
        )
        assert (await statuses(db_engine, order.order_id))[0] == "partially_refunded"
        ok(create(client, order.order_id, [(phys, 1000)]), 201)
        assert await statuses(db_engine, order.order_id) == ("refunded", "refunded")

        other = await paid_online(db_session)
        assert other.stl is not None
        ok(create(client, other.order_id, [(other.physical[0], 1000)]), 201)
        assert await line_state(db_engine, other.stl) == "awaiting_delivery"
        assert (await statuses(db_engine, other.order_id))[0] == "partially_refunded"
        failing = ok(create(client, other.order_id, [(other.stl, 500)]), 201)["id"]
        ok(act(client, failing, "fail", {"reason": "Bounced."}))
    assert await statuses(db_engine, other.order_id) == ("partially_refunded", "partially_refunded")


async def test_i13_stl_refunded_first_then_the_physical_line_ships(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, physical=("pending",))
    assert order.stl is not None
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 500)]), 201)
        seeded = PhysicalOrder(order.order_id, order.user_id, "", order.physical, order.phone)
        for target in ("in_production", "ready_to_ship", "shipped", "delivered"):
            assert move(client, seeded, target).status_code == 200, target
    assert (await statuses(db_engine, order.order_id))[0] == "partially_refunded"


async def test_i14_stl_delivery_after_partial_and_full_refunds(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, physical=("delivered",))
    assert order.stl is not None
    seeded = PhysicalOrder(order.order_id, order.user_id, "", (order.stl,), order.phone)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        ok(create(client, order.order_id, [(order.stl, 100)]), 201)
        assert move(client, seeded, "delivered").status_code == 200
    full = await paid_online(db_session, physical=("delivered",))
    assert full.stl is not None
    product = await db_session.scalar(
        text("SELECT product_id FROM order_items WHERE id = :i"), {"i": full.stl}
    )
    seeded = PhysicalOrder(full.order_id, full.user_id, "", (full.stl,), full.phone)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refund = ok(create(client, full.order_id, [(full.stl, 500)]), 201)["id"]
        closed = move(client, seeded, "delivered")
        assert_problem(closed, 409, "INVALID_STATE_TRANSITION")
        assert closed.json()["reason"] == "line_closed"
        ok(act(client, refund, "fail", {"reason": "Bounced."}))
    await db_session.rollback()
    assert not await stl_owned(db_session, user_id=full.user_id, product_id=product)


# --- unfinished lines, unknown lines -------------------------------------------------------


@pytest.mark.parametrize(
    "state", ["pending", "in_production", "ready_to_ship", "shipped", "ready_for_pickup"]
)
async def test_a_full_refund_of_an_unfinished_line_needs_a_cancellation(
    state: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    fulfillment = "pickup" if state == "ready_for_pickup" else "delivery"
    order = await paid_online(db_session, physical=(state,), stl=None, fulfillment=fulfillment)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        refused = create(client, order.order_id, [(line, 1000)])
        assert_problem(refused, 422, "REFUND_REQUIRES_CANCELLATION")
        assert refused.json()["order_item_ids"] == [str(line)]
        ok(create(client, order.order_id, [(line, 999)]), 201)
    assert await line_state(db_engine, line) == state


async def test_a_line_of_another_order_is_404(db_session: AsyncSession) -> None:
    order, other = await paid_online(db_session, stl=None), await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(create(client, order.order_id, [(other.physical[0], 1)]), 404)
        assert_problem(create(client, uuid.uuid4(), [(other.physical[0], 1)]), 404)
        assert_problem(act(client, uuid.uuid4(), "settle", {}), 404)


async def test_duplicate_lines_and_hostile_amounts_are_422(db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    with client_for(main_app) as client:
        await _admin(client, db_session)
        assert_problem(create(client, order.order_id, [(line, 1), (line, 2)]), 422)
        for amount in (0, -1, 10**12):
            assert_problem(create(client, order.order_id, [(line, amount)]), 422)
        response = client.post(
            f"{ADMIN}/orders/{order.order_id}/refunds",
            json={"items": [], "reason": "x", "extra": 1},
            headers=csrf(client) | {"Idempotency-Key": key()},
        )
    assert_problem(response, 422)


# --- I21 ----------------------------------------------------------------------------------


async def test_i21_the_customer_sees_a_refund_summary(db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    email = await db_session.scalar(
        text("SELECT email FROM users WHERE id = :u"), {"u": order.user_id}
    )
    with client_for(main_app) as client:
        await _admin(client, db_session)
        settled = ok(create(client, order.order_id, [(a, 300)]), 201)["id"]
        ok(act(client, settled, "settle", {}))
        ok(create(client, order.order_id, [(b, 200)]), 201)
        voided = ok(create(client, order.order_id, [(b, 50)]), 201)["id"]
        ok(act(client, voided, "void", {"reason": "Entered twice."}))
    stranger = await create_user(db_session)
    with client_for(main_app) as customer:
        login(customer, str(email))
        body = ok(customer.get(f"/api/v1/me/orders/{order.order_id}"))
    assert [(r["kind"], r["status"], r["amount"]["amount_cents"]) for r in body["refunds"]] == [
        ("admin", "refunded", 300),
        ("admin", "processing", 200),
    ]
    with client_for(main_app) as other:
        login(other, stranger.email)
        assert_problem(other.get(f"/api/v1/me/orders/{order.order_id}"), 404)


async def test_the_admin_order_detail_lists_refunds_and_balances(db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await _admin(client, db_session)
        before = ok(client.get(f"{ADMIN}/orders/{order.order_id}"))
        assert before["refunds"] == []
        assert before["refund_balance"]["payment_cents"] == 1000
        ok(create(client, order.order_id, [(order.physical[0], 250)]), 201)
        after = ok(client.get(f"{ADMIN}/orders/{order.order_id}"))
    assert [(r["status"], r["amount"]["amount_cents"]) for r in after["refunds"]] == [
        ("pending", 250)
    ]
    assert after["refund_balance"] == {
        "lines": [{"order_item_id": str(order.physical[0]), "balance_cents": 750}],
        "payment_cents": 750,
    }


# --- S3 -----------------------------------------------------------------------------------


def test_s3_the_provider_port_has_no_refund_method() -> None:
    names = {name for name in dir(PaymentProviderPort) if not name.startswith("_")}
    assert names and not {name for name in names if "refund" in name.lower()}, names
