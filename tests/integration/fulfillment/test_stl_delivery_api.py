"""VS-023b over HTTP: the STL delivery queue and the mark-as-sent transition (plan 6)."""

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.ordering.infrastructure.orders import stl_delivery_query
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
from tests.integration.fulfillment.delivery_support import (
    EPOCH,
    QUEUE,
    effects,
    line_of,
    line_row,
    seed_stl_order,
    transition_path,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

BODY = {"target_status": "delivered"}


def _send(client: TestClient, order: uuid.UUID, item: uuid.UUID, **over: Any) -> httpx.Response:
    response: httpx.Response = client.post(
        transition_path(order, item), json=BODY, headers=csrf(client) | over
    )
    return response


def _page(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(QUEUE, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- the queue ------------------------------------------------------------------------------


async def test_only_awaiting_stl_lines_are_queued(db_session: AsyncSession) -> None:
    buyer = (await create_user(db_session)).id
    queued, queued_line = await seed_stl_order(db_session, user_id=buyer)
    for status in ("pending", "delivered", "refunded", "cancelled"):
        await seed_stl_order(db_session, user_id=buyer, line_status=status)
    physical = await seed_stl_order(db_session, user_id=buyer, line_status="pending", physical=True)
    assert physical[0].order_id != queued.order_id
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        items = _page(client, customer_id=str(buyer))["items"]
    assert [item["item_id"] for item in items] == [str(queued_line)]


async def test_the_queue_is_oldest_first_and_paging_loses_and_repeats_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = (await create_user(db_session)).id
    stamps = [EPOCH + timedelta(minutes=m) for m in (5, 1, 3, 3, 2)]  # two share a moment
    lines = [(await seed_stl_order(db_session, user_id=buyer, queued_at=t))[1] for t in stamps]
    expected = [
        str(i) for _, i in sorted(zip(stamps, lines, strict=True), key=lambda p: (p[0], str(p[1])))
    ]
    seen: list[str] = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        page = _page(client, customer_id=str(buyer), limit=2)
        seen += [item["item_id"] for item in page["items"]]
        # A line leaves the queue between pages: it must not disturb the rest.
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE order_items SET fulfillment_status = 'refunded' WHERE id = :i"),
                {"i": expected[3]},
            )
        while page["next_cursor"]:
            page = _page(client, customer_id=str(buyer), limit=2, cursor=page["next_cursor"])
            seen += [item["item_id"] for item in page["items"]]
    assert seen == [i for i in expected if i != expected[3]]


async def test_a_queue_row_carries_the_admin_fields_and_nothing_else(
    db_session: AsyncSession,
) -> None:
    order, line = await seed_stl_order(db_session, queued_at=EPOCH, email="send-to-me@example.com")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        (item,) = _page(client, customer_id=str(order.user_id))["items"]
    assert set(item) == {
        "item_id",
        "order_id",
        "order_number",
        "product_id",
        "product_name",
        "customer_id",
        "customer_email",
        "line_total_cents",
        "currency",
        "queued_at",
    }
    assert (item["item_id"], item["customer_email"]) == (str(line), "send-to-me@example.com")
    assert (item["order_number"], item["customer_id"]) == (order.order_number, str(order.user_id))


@pytest.mark.parametrize(
    "cursor", ["not-a-cursor", "!!!", base64.urlsafe_b64encode(b"x|y").decode()]
)
async def test_a_bad_cursor_is_a_422(cursor: str, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(QUEUE, params={"cursor": cursor})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_the_queue_query_uses_the_partial_index(db_engine: AsyncEngine) -> None:
    query = stl_delivery_query(after=None, limit=26, product_id=None, user_id=None)
    compiled = query.compile(compile_kwargs={"render_postcompile": True})
    async with db_engine.connect() as conn:
        await conn.execute(text("ANALYZE order_items, orders"))
        await conn.commit()
        await conn.execute(text("SET enable_seqscan = off"))
        rows = await conn.execute(text(f"EXPLAIN {compiled}"), dict(compiled.params))
        plan = "\n".join(str(row[0]) for row in rows)
        await conn.rollback()
    assert "ix_order_items_stl_awaiting" in plan, plan


# --- authorization --------------------------------------------------------------------------


async def test_both_routes_refuse_anonymous_customer_and_unverified_mfa(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session)
    customer = await create_user(db_session)
    admin_without_mfa = await create_user(db_session, role=UserRole.ADMIN)
    results: dict[str, tuple[int, int]] = {}
    with client_for(main_app) as anonymous:
        results["anonymous"] = (
            anonymous.get(QUEUE).status_code,
            anonymous.post(transition_path(order.order_id, line), json=BODY).status_code,
        )
    with client_for(main_app) as client:
        login(client, customer.email, PASSWORD)
        results["customer"] = (
            client.get(QUEUE).status_code,
            _send(client, order.order_id, line).status_code,
        )
    with client_for(main_app) as client:
        login(client, admin_without_mfa.email, PASSWORD)
        results["no_mfa"] = (
            client.get(QUEUE).status_code,
            _send(client, order.order_id, line).status_code,
        )
    assert results == {"anonymous": (401, 401), "customer": (404, 404), "no_mfa": (401, 401)}
    assert (await line_row(db_engine, line)).fulfillment_status == "awaiting_delivery"


async def test_a_delivery_without_a_csrf_token_is_refused(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(transition_path(order.order_id, line), json=BODY)
    assert_problem(response, 403, "CSRF_INVALID")
    assert (await line_row(db_engine, line)).fulfillment_status == "awaiting_delivery"
    assert await effects(db_engine, line) == (0, 0, 0, 0)


# --- the transition -------------------------------------------------------------------------


async def test_marking_a_line_sent_writes_every_record_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session, email="buyer-23b@example.com")
    before = datetime.now(UTC)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        response = _send(client, order.order_id, line)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["fulfillment_status"], body["order_status"]) == ("delivered", "completed")
    assert body["delivered_by"] == str(admin.id)
    row = await line_row(db_engine, line)
    assert (row.fulfillment_status, row.delivered_by, row.order_status) == (
        "delivered",
        admin.id,
        "completed",
    )
    assert row.fulfilled_at >= before
    assert await effects(db_engine, line) == (1, 1, 1, 1)
    async with db_engine.connect() as conn:
        history = (
            await conn.execute(
                text(
                    "SELECT from_status, to_status, actor_user_id FROM order_status_history"
                    " WHERE order_item_id = :i"
                ),
                {"i": line},
            )
        ).one()
        order_rows = (
            await conn.execute(
                text(
                    "SELECT to_status, actor_user_id FROM order_status_history"
                    " WHERE order_id = :o AND order_item_id IS NULL ORDER BY created_at"
                ),
                {"o": order.order_id},
            )
        ).all()
        audit = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, request_id, ip_hash, after_data FROM audit_logs"
                    " WHERE action = 'stl.delivered' AND entity_id = :i"
                ),
                {"i": line},
            )
        ).one()
        note = (
            await conn.execute(
                text(
                    "SELECT user_id, type FROM notifications"
                    " WHERE payload->>'item_id' = CAST(:i AS text)"
                ),
                {"i": str(line)},
            )
        ).one()
        mail = (
            await conn.execute(
                text(
                    "SELECT recipient_email, status FROM email_outbox"
                    " WHERE template = 'order_stl_delivered'"
                    " AND payload->>'item_id' = CAST(:i AS text)"
                ),
                {"i": str(line)},
            )
        ).one()
    assert tuple(history) == ("awaiting_delivery", "delivered", admin.id)
    assert [tuple(r) for r in order_rows] == [("completed", admin.id)]
    assert audit.actor_user_id == admin.id and audit.request_id and audit.ip_hash
    assert audit.after_data["delivered_by"] == str(admin.id)
    assert (note.user_id, note.type) == (order.user_id, "download")
    # The email waits in the outbox: nothing external happened inside the transaction.
    assert (mail.recipient_email, mail.status) == ("buyer-23b@example.com", "pending")


async def test_a_pending_physical_line_keeps_the_order_in_progress(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session, physical=True)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _send(client, order.order_id, line)
    assert response.status_code == 200, response.text
    assert response.json()["order_status"] == "in_progress"
    async with db_engine.connect() as conn:
        order_rows = await conn.scalar(
            text(
                "SELECT count(*) FROM order_status_history"
                " WHERE order_id = :o AND order_item_id IS NULL"
            ),
            {"o": order.order_id},
        )
    assert order_rows == 0, "the order status did not change, so no order history row"


async def test_delivery_on_a_partly_refunded_order_keeps_it_partially_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The stop-gap: VS-030 must compute the refund inputs from real refunds."""
    order, line = await seed_stl_order(db_session, order_status="partially_refunded")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _send(client, order.order_id, line)
    assert response.status_code == 200, response.text
    assert (await line_row(db_engine, line)).order_status == "partially_refunded"


@pytest.mark.parametrize(
    ("line_status", "reason"),
    [
        ("delivered", "already_delivered"),
        ("refunded", "line_closed"),
        ("cancelled", "line_closed"),
        ("pending", "not_awaiting_delivery"),
    ],
)
async def test_a_line_that_is_not_awaiting_delivery_is_a_409_that_writes_nothing(
    line_status: str, reason: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, line = await seed_stl_order(db_session, line_status=line_status)
    before = await line_row(db_engine, line)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _send(client, order.order_id, line)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == reason
    assert ("fulfilled_at" in response.json()) is (line_status == "delivered")
    assert tuple(await line_row(db_engine, line)) == tuple(before)
    assert await effects(db_engine, line) == (0, 0, 0, 0)


async def test_a_physical_line_is_a_409_and_stays_untouched(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, _ = await seed_stl_order(db_session, physical=True)
    lamp = await line_of(db_session, order.order_id, "physical")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _send(client, order.order_id, lamp)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "not_an_stl_line"
    assert (await line_row(db_engine, lamp)).fulfillment_status == "pending"
    assert await effects(db_engine, lamp) == (0, 0, 0, 0)


async def test_unknown_order_unknown_item_and_a_foreign_item_share_one_404(
    db_session: AsyncSession,
) -> None:
    order, line = await seed_stl_order(db_session)
    other, other_line = await seed_stl_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        replies = [
            _send(client, uuid.uuid4(), line),
            _send(client, order.order_id, uuid.uuid4()),
            _send(client, order.order_id, other_line),
        ]
    assert [r.status_code for r in replies] == [404, 404, 404]
    shapes = {(r.json()["code"], r.json()["title"], r.json()["detail"]) for r in replies}
    assert len(shapes) == 1
    assert other.order_id != order.order_id


async def test_a_failing_notice_rolls_the_whole_delivery_back(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    order, line = await seed_stl_order(db_session)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("notification store down")

    monkeypatch.setattr("app.fulfillment.infrastructure.delivery_side.create_notification", boom)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = _send(client, order.order_id, line)
    assert response.status_code == 500
    row = await line_row(db_engine, line)
    assert (row.fulfillment_status, row.fulfilled_at, row.delivered_by) == (
        "awaiting_delivery",
        None,
        None,
    )
    assert row.order_status == "in_progress"
    assert await effects(db_engine, line) == (0, 0, 0, 0)


async def test_an_unknown_target_status_is_a_422(db_session: AsyncSession) -> None:
    order, line = await seed_stl_order(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(
            transition_path(order.order_id, line),
            json={"target_status": "shipped"},
            headers=csrf(client),
        )
    assert_problem(response, 422, "VALIDATION_ERROR")
