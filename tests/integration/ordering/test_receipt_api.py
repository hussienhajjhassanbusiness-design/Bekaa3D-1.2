"""VS-029b over HTTP: `POST /api/v1/me/orders/{id}/confirm-receipt` and `…/report-problem`
(SRS 8.8, BR-147, FR-21, F-069; ADR-041)."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.engagement.infrastructure.repositories import NotificationRepository
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    async_client,
    create_user,
    running_app,
)
from tests.integration.fulfillment.delivery_support import admin_client
from tests.integration.fulfillment.order_support import (
    PhysicalOrder,
    handover_path,
    seed_physical_order,
    states,
)
from tests.integration.ordering.receipt_support import (
    ACTIONS,
    CONFIRM,
    DONE,
    EVENT,
    REPORT,
    act,
    action_path,
    active_admin_ids,
    body_for,
    linked_messages,
    problem_notices,
    receipt_audits,
    stamps,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

NOT_RECEIVED = ["pending", "in_production", "ready_to_ship", "shipped", "ready_for_pickup"]


async def _login(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


@asynccontextmanager
async def _customer(
    make_app: Callable[[], FastAPI], user: UserModel
) -> AsyncIterator[httpx.AsyncClient]:
    async with running_app(make_app) as app:
        client = async_client(app)
        try:
            await _login(client, user.email)
            yield client
        finally:
            await client.aclose()


async def _order(db: AsyncSession, user: UserModel, **over: Any) -> PhysicalOrder:
    return await seed_physical_order(db, user_id=user.id, email=user.email, **over)


async def _history_count(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM order_status_history WHERE order_id = :o"), {"o": order_id}
        )
    return int(count or 0)


def _line(body: dict[str, Any], line_id: uuid.UUID) -> dict[str, Any]:
    return next(line for line in body["lines"] if line["id"] == str(line_id))


@pytest.mark.parametrize("payment", ["cash", "online"])
@pytest.mark.parametrize("fulfillment", ["delivery", "pickup"])
async def test_confirm_stamps_only_the_received_physical_lines(
    fulfillment: str,
    payment: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    online = {"payment_status": "paid", "stl_line": "delivered"} if payment == "online" else {}
    order = await _order(
        db_session,
        user,
        payment_method=payment,
        fulfillment=fulfillment,
        line_states=[DONE[fulfillment], "cancelled", "pending"],
        **online,
    )
    before_status = await states(db_engine, order.order_id)
    before_history = await _history_count(db_engine, order.order_id)
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, CONFIRM)
    assert response.status_code == 200, response.text
    body = response.json()
    received, cancelled, pending = (_line(body, i) for i in order.line_ids)
    assert received["receipt_confirmed_at"] is not None
    assert received["problem_reported_at"] is None
    assert cancelled["receipt_confirmed_at"] is None and pending["receipt_confirmed_at"] is None
    stl = [line for line in body["lines"] if line["product_type"] == "stl"]
    assert all(line["receipt_confirmed_at"] is None for line in stl)
    assert await _stamped_ids(db_engine, order.order_id) == [order.line_ids[0]]
    # no state change, no history row; one audit row naming the stamped line
    assert await states(db_engine, order.order_id) == before_status
    assert await _history_count(db_engine, order.order_id) == before_history
    assert body["status"] == before_status[0]
    [audit] = await receipt_audits(db_engine, order.order_id)
    assert (audit.action, audit.actor_user_id) == ("order.receipt_confirmed", user.id)
    assert audit.after_data["line_ids"] == [str(order.line_ids[0])]


async def _stamped_ids(engine: AsyncEngine, order_id: uuid.UUID) -> list[uuid.UUID]:
    async with engine.connect() as conn:
        rows = await conn.scalars(
            text(
                "SELECT id FROM order_items WHERE order_id = :o"
                " AND receipt_confirmed_at IS NOT NULL ORDER BY id"
            ),
            {"o": order_id},
        )
        return list(rows)


async def test_confirming_twice_keeps_the_first_timestamp(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["shipped"])
    await _set_state(db_engine, order.line_ids[0], "delivered")
    async with _customer(make_app, user) as client:
        first = await act(client, order.order_id, CONFIRM)
        second = await act(client, order.order_id, CONFIRM)
    assert (first.status_code, second.status_code) == (200, 200), second.text
    assert first.json()["lines"] == second.json()["lines"]
    assert len(await receipt_audits(db_engine, order.order_id)) == 1


async def test_a_line_received_after_the_first_confirm_is_stamped_on_the_next(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered", "shipped"])
    async with _customer(make_app, user) as client:
        first = (await act(client, order.order_id, CONFIRM)).json()
        await _set_state(db_engine, order.line_ids[1], "delivered")
        second = (await act(client, order.order_id, CONFIRM)).json()
    early, late = order.line_ids
    assert (
        _line(second, early)["receipt_confirmed_at"] == _line(first, early)["receipt_confirmed_at"]
    )
    assert _line(first, late)["receipt_confirmed_at"] is None
    assert _line(second, late)["receipt_confirmed_at"] is not None
    audits = await receipt_audits(db_engine, order.order_id)
    assert [a.after_data["line_ids"] for a in audits] == [[str(early)], [str(late)]]


async def _set_state(engine: AsyncEngine, line_id: uuid.UUID, state: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE order_items SET fulfillment_status = CAST(:s AS order_item_status)"
                " WHERE id = :i"
            ),
            {"s": state, "i": line_id},
        )


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("state", [*NOT_RECEIVED, "cancelled"])
async def test_an_order_with_nothing_received_refuses_both_actions(
    action: str,
    state: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    fulfillment = "pickup" if state == "ready_for_pickup" else "delivery"
    order = await _order(db_session, user, fulfillment=fulfillment, line_states=[state])
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, action)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "no_delivered_line"
    await _assert_nothing_written(db_engine, order.order_id)


@pytest.mark.parametrize("action", ACTIONS)
async def test_a_delivered_stl_line_alone_is_not_a_receipt(
    action: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    """ADR-041 d1: an STL "delivered" means the file was emailed, not received."""
    user = await create_user(db_session)
    order = await _order(
        db_session,
        user,
        payment_method="online",
        payment_status="paid",
        line_states=["cancelled"],
        stl_line="delivered",
    )
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, action)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    await _assert_nothing_written(db_engine, order.order_id)


async def _assert_nothing_written(engine: AsyncEngine, order_id: uuid.UUID) -> None:
    assert all(stamp == (None, None) for stamp in await stamps(engine, order_id))
    assert await linked_messages(engine, order_id) == []
    assert await problem_notices(engine, order_id) == []
    assert await receipt_audits(engine, order_id) == []


@pytest.mark.parametrize("action", ACTIONS)
async def test_another_customers_order_and_an_unknown_id_are_the_same_404(
    action: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    owner, other = await create_user(db_session), await create_user(db_session)
    order = await _order(db_session, owner, line_states=["delivered"])
    async with _customer(make_app, other) as client:
        theirs = await act(client, order.order_id, action)
        unknown = await act(client, uuid.uuid4(), action)
    assert_problem(theirs, 404, "NOT_FOUND")
    assert_problem(unknown, 404, "NOT_FOUND")
    assert theirs.json()["detail"] == unknown.json()["detail"]
    await _assert_nothing_written(db_engine, order.order_id)


@pytest.mark.parametrize("fulfillment", ["delivery", "pickup"])
async def test_a_report_queues_a_linked_message_and_stamps_the_received_lines(
    fulfillment: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    order = await _order(
        db_session, user, fulfillment=fulfillment, line_states=[DONE[fulfillment], "pending"]
    )
    before = await states(db_engine, order.order_id)
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, REPORT, message="  Cracked base.\nHelp!  ")
    assert response.status_code == 201, response.text
    received, pending = (_line(response.json(), i) for i in order.line_ids)
    assert received["problem_reported_at"] is not None and pending["problem_reported_at"] is None
    assert received["receipt_confirmed_at"] is None
    [message] = await linked_messages(db_engine, order.order_id)
    assert (message.user_id, message.order_id, message.email) == (
        user.id,
        order.order_id,
        user.email,
    )
    expected_name = "Rana" if fulfillment == "delivery" else user.email.rpartition("@")[0]
    assert message.name == expected_name
    assert message.subject == f"Problem with order {order.order_number}"
    assert (message.message, message.phone, message.status) == ("Cracked base.\nHelp!", None, "new")
    assert await states(db_engine, order.order_id) == before
    [audit] = await receipt_audits(db_engine, order.order_id)
    assert audit.action == "order.problem_reported"
    assert audit.after_data == {
        "order_number": order.order_number,
        "line_ids": [str(order.line_ids[0])],
        "contact_message_id": str(message.id),
    }


async def test_a_report_notifies_every_active_administrator_exactly_once(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    inactive = await create_user(db_session, role=UserRole.ADMIN, active=False)
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    admins = await active_admin_ids(db_engine)
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, REPORT, message="secret body text")
    assert response.status_code == 201, response.text
    notices = await problem_notices(db_engine, order.order_id)
    recipients = [notice.user_id for notice in notices]
    assert sorted(recipients) == sorted(admins) and len(recipients) == len(set(recipients))
    assert inactive.id not in recipients and user.id not in recipients
    [message] = await linked_messages(db_engine, order.order_id)
    for notice in notices:
        assert notice.type == "order"
        assert notice.payload == {
            "event": EVENT,
            "order_id": str(order.order_id),
            "order_number": order.order_number,
            "contact_message_id": str(message.id),
            "title": f"Problem reported on order {order.order_number}",
        }
        assert "secret" not in str(notice.payload) and user.email not in str(notice.payload)


async def test_a_second_report_adds_a_message_but_keeps_the_first_timestamp(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["picked_up"], fulfillment="pickup")
    async with _customer(make_app, user) as client:
        first = await act(client, order.order_id, REPORT, message="First.")
        second = await act(client, order.order_id, REPORT, message="Still broken.")
    assert (first.status_code, second.status_code) == (201, 201), second.text
    assert first.json()["lines"] == second.json()["lines"]
    messages = await linked_messages(db_engine, order.order_id)
    assert [m.message for m in messages] == ["First.", "Still broken."]
    audits = await receipt_audits(db_engine, order.order_id)
    assert [a.after_data["line_ids"] for a in audits] == [[str(order.line_ids[0])], []]
    assert len(await problem_notices(db_engine, order.order_id)) == 2 * len(
        await active_admin_ids(db_engine)
    )


async def test_a_failed_notification_rolls_the_whole_report_back(
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-041 d4: the message, its notifications and the stamps commit together."""
    await create_user(db_session, role=UserRole.ADMIN)
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])

    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("notifications table unavailable")

    monkeypatch.setattr(NotificationRepository, "add", broken)
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, REPORT)
    assert response.status_code == 500
    await _assert_nothing_written(db_engine, order.order_id)


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   \n "},
        {"message": "x" * 5001},
        {"message": "bad\x00byte"},
        {"message": "fine", "phone": "+96170000000"},
        {},
    ],
    ids=["empty", "blank", "too-long", "nul", "extra-field", "missing"],
)
async def test_a_malformed_report_is_422_and_stores_nothing(
    body: dict[str, Any],
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    async with _customer(make_app, user) as client:
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        response = await client.post(
            action_path(order.order_id, REPORT), json=body, headers=headers
        )
    assert_problem(response, 422, "VALIDATION_ERROR")
    await _assert_nothing_written(db_engine, order.order_id)


async def test_a_5000_character_report_is_accepted(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    async with _customer(make_app, user) as client:
        response = await act(client, order.order_id, REPORT, message="y" * 5000)
    assert response.status_code == 201, response.text
    assert len((await linked_messages(db_engine, order.order_id))[0].message) == 5000


@pytest.mark.parametrize("action", ACTIONS)
async def test_anonymous_unverified_and_csrf_less_callers_change_nothing(
    action: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    unverified = await create_user(db_session, verified=False)
    order = await _order(db_session, user, line_states=["delivered"])
    theirs = await _order(db_session, unverified, line_states=["delivered"])
    path = action_path(order.order_id, action)
    async with running_app(make_app) as app:
        async with async_client(app) as anonymous:
            assert_problem(await anonymous.post(path, json=body_for(action)), 401)
        async with async_client(app) as client:
            await _login(client, user.email)
            assert_problem(await client.post(path, json=body_for(action)), 403, "CSRF_INVALID")
        async with async_client(app) as client:
            await _login(client, unverified.email)
            refused = await act(client, theirs.order_id, action)
            assert_problem(refused, 403, "EMAIL_VERIFICATION_REQUIRED")
    await _assert_nothing_written(db_engine, order.order_id)
    await _assert_nothing_written(db_engine, theirs.order_id)


async def test_following_the_email_link_with_a_get_changes_nothing(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    async with _customer(make_app, user) as client:
        page = await client.get(f"/api/v1/me/orders/{order.order_id}")
        for action in ACTIONS:
            assert (await client.get(action_path(order.order_id, action))).status_code == 405
    assert page.status_code == 200
    await _assert_nothing_written(db_engine, order.order_id)


async def test_the_sixth_report_in_an_hour_is_rate_limited(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    async with _customer(make_app, user) as client:
        codes = [(await act(client, order.order_id, REPORT)).status_code for _ in range(5)]
        limited = await act(client, order.order_id, REPORT)
        confirm = await act(client, order.order_id, CONFIRM)
    assert codes == [201] * 5
    assert_problem(limited, 429, "RATE_LIMITED")
    assert len(await linked_messages(db_engine, order.order_id)) == 5
    assert confirm.status_code == 200, "confirm has no rate limit"


async def test_a_cash_order_completes_through_the_handover_with_no_confirmation(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """BR-147 / Done when: confirmation never blocks completion, nor changes it after."""
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["shipped"], line_totals=[1500])
    async with running_app(make_app) as app:
        admin, _ = await admin_client(app, db_session)
        try:
            headers = {"X-CSRF-Token": admin.cookies["csrf_token"]}
            handover = await admin.post(
                handover_path(order.order_id),
                json={"amount_cents": 1500, "currency": "USD"},
                headers=headers,
            )
        finally:
            await admin.aclose()
    assert handover.status_code == 200, handover.text
    assert await states(db_engine, order.order_id) == ("completed", ["delivered"])
    assert await stamps(db_engine, order.order_id) == [(None, None)]
    async with _customer(make_app, user) as client:
        detail = (await client.get(f"/api/v1/me/orders/{order.order_id}")).json()
        confirmed = (await act(client, order.order_id, CONFIRM)).json()
    assert (confirmed["status"], confirmed["completed_at"]) == ("completed", detail["completed_at"])


async def test_the_administrator_sees_both_on_the_order_and_the_message(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await _order(db_session, user, line_states=["delivered"])
    async with _customer(make_app, user) as client:
        await act(client, order.order_id, CONFIRM)
        await act(client, order.order_id, REPORT)
    [message] = await linked_messages(db_engine, order.order_id)
    async with running_app(make_app) as app:
        admin, _ = await admin_client(app, db_session)
        try:
            detail = (await admin.get(f"/api/v1/admin/orders/{order.order_id}")).json()
            queued = (await admin.get(f"/api/v1/admin/contact-messages/{message.id}")).json()
        finally:
            await admin.aclose()
    [line] = detail["lines"]
    assert line["receipt_confirmed_at"] is not None and line["problem_reported_at"] is not None
    assert (queued["order_id"], queued["user_id"]) == (str(order.order_id), str(user.id))
