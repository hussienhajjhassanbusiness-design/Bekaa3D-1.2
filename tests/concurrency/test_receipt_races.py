"""VS-029b races on real Postgres (FR-21 concurrency; ADR-024 d9, ADR-041). As VS-029's,
each racer waits on the held `orders` row lock before it is released, so they overlap."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.infrastructure.models import UserModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.test_admin_order_races import order_lock, queued
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.fulfillment.delivery_support import admin_client
from tests.integration.fulfillment.order_support import (
    PhysicalOrder,
    handover_path,
    seed_physical_order,
    states,
    transition_path,
)
from tests.integration.ordering.receipt_support import (
    CONFIRM,
    REPORT,
    act,
    active_admin_ids,
    linked_messages,
    problem_notices,
    receipt_audits,
    stamps,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]


async def _customers(app: FastAPI, user: UserModel, count: int) -> list[httpx.AsyncClient]:
    clients = []
    for _ in range(count):
        client = async_client(app)
        login = await client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        clients.append(client)
    return clients


def _action(client: httpx.AsyncClient, order: PhysicalOrder, action: str, **body: Any) -> Any:
    async def call() -> httpx.Response:
        return await act(client, order.order_id, action, **body)

    return call


def _admin_post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> Any:
    async def call() -> httpx.Response:
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        return await client.post(path, json=body, headers=headers)

    return call


async def test_two_confirms_at_once_keep_one_timestamp_and_one_audit_row(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=user.id, line_states=["delivered"])
    async with running_app(make_app) as app:
        clients = await _customers(app, user, 2)
        try:
            first, second = await queued(
                db_engine, order.order_id, *(_action(c, order, CONFIRM) for c in clients)
            )
        finally:
            for client in clients:
                await client.aclose()
    assert (first.status_code, second.status_code) == (200, 200), second.text
    assert first.json()["lines"] == second.json()["lines"]
    assert len(await receipt_audits(db_engine, order.order_id)) == 1


async def test_two_reports_at_once_queue_two_messages_and_keep_the_first_timestamp(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=user.id, line_states=["delivered"])
    async with running_app(make_app) as app:
        clients = await _customers(app, user, 2)
        try:
            first, second = await queued(
                db_engine,
                order.order_id,
                _action(clients[0], order, REPORT, message="One."),
                _action(clients[1], order, REPORT, message="Two."),
            )
        finally:
            for client in clients:
                await client.aclose()
    assert (first.status_code, second.status_code) == (201, 201), second.text
    assert first.json()["lines"] == second.json()["lines"]
    assert [m.message for m in await linked_messages(db_engine, order.order_id)] == ["One.", "Two."]
    audits = await receipt_audits(db_engine, order.order_id)
    assert [len(a.after_data["line_ids"]) for a in audits] == [1, 0]
    notices = await problem_notices(db_engine, order.order_id)
    assert len(notices) == 2 * len(await active_admin_ids(db_engine))


@pytest.mark.parametrize("confirm_first", [True, False])
async def test_a_confirm_racing_the_cash_handover_sees_the_lines_it_locked(
    confirm_first: bool,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    """Both take `orders` first (ADR-024 d9): no deadlock, and the confirm re-reads."""
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session, user_id=user.id, line_states=["shipped"], line_totals=[900]
    )
    async with running_app(make_app) as app:
        admin, _ = await admin_client(app, db_session)
        [customer] = await _customers(app, user, 1)
        handover = _admin_post(
            admin, handover_path(order.order_id), {"amount_cents": 900, "currency": "USD"}
        )
        confirm = _action(customer, order, CONFIRM)
        try:
            racers = (confirm, handover) if confirm_first else (handover, confirm)
            results = await queued(db_engine, order.order_id, *racers)
        finally:
            await admin.aclose()
            await customer.aclose()
    confirmed, handed = results if confirm_first else results[::-1]
    assert handed.status_code == 200, handed.text
    assert await states(db_engine, order.order_id) == ("completed", ["delivered"])
    [(confirmed_at, _)] = await stamps(db_engine, order.order_id)
    if confirm_first:
        assert confirmed.status_code == 409 and confirmed_at is None
    else:
        assert confirmed.status_code == 200 and confirmed_at is not None


async def test_a_report_racing_a_transition_on_another_line_has_both_outcomes(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=user.id,
        payment_method="online",
        payment_status="paid",
        line_states=["delivered", "ready_to_ship"],
    )
    async with running_app(make_app) as app:
        admin, _ = await admin_client(app, db_session)
        [customer] = await _customers(app, user, 1)
        move = _admin_post(
            admin,
            transition_path(order.order_id, order.line_ids[1]),
            {"target_status": "shipped"},
        )
        try:
            reported, moved = await queued(
                db_engine, order.order_id, _action(customer, order, REPORT), move
            )
        finally:
            await admin.aclose()
            await customer.aclose()
    assert (reported.status_code, moved.status_code) == (201, 200), moved.text
    _, lines = await states(db_engine, order.order_id)
    assert sorted(lines) == ["delivered", "shipped"]
    assert len(await linked_messages(db_engine, order.order_id)) == 1


@pytest.mark.parametrize("action", [CONFIRM, REPORT])
async def test_another_customers_locked_order_is_a_404_without_waiting(
    action: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    """Money review finding 3: ownership is in the lock's WHERE, so a foreign row is
    never locked or waited on, even while an administrator holds it."""
    owner, caller = await create_user(db_session), await create_user(db_session)
    order = await seed_physical_order(db_session, user_id=owner.id, line_states=["delivered"])
    async with running_app(make_app) as app, order_lock(db_engine, order.order_id):
        [client] = await _customers(app, caller, 1)
        try:
            response = await asyncio.wait_for(act(client, order.order_id, action), timeout=3)
        finally:
            await client.aclose()
    assert response.status_code == 404, response.text
    assert await stamps(db_engine, order.order_id) == [(None, None)]
