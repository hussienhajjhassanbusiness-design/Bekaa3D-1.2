"""VS-029 races on real Postgres. Each racer is made to wait on the `orders` row lock first,
so the transactions overlap; the order they queue in decides the winner, and the loser
re-reads under the lock (ADR-024 d9). A deadlock or lock wait would fail on its timeout."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.exceptions import CashAlreadyRecordedError
from app.payments.infrastructure.cash_payments import insert_cash_payment
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.reconcile import reconcile_stuck
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user, running_app
from tests.integration.fulfillment.delivery_support import admin_client, wait_for_lock_waiters
from tests.integration.fulfillment.order_support import (
    PhysicalOrder,
    effects,
    handover_path,
    seed_physical_order,
    states,
    transition_path,
)
from tests.integration.ordering.physical_support import random_phone, seed_block
from tests.integration.payments.recovery_support import (
    YEARS_AHEAD,
    factory,
    keyset_start,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
RACE_TIMEOUT_SECONDS = 20


def epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 7, 1, tzinfo=UTC)


@asynccontextmanager
async def order_lock(engine: AsyncEngine, order_id: uuid.UUID) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT id FROM orders WHERE id = :o FOR UPDATE"), {"o": order_id})
        try:
            yield conn
        finally:
            await conn.rollback()


async def queued(
    engine: AsyncEngine, order_id: uuid.UUID, *racers: Callable[[], Coroutine[Any, Any, Any]]
) -> list[Any]:
    """Start each racer only once the previous one waits on the held order lock, then
    release it: Postgres grants a row lock to its waiters in the order they queued."""
    async with order_lock(engine, order_id) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            await wait_for_lock_waiters(engine, n)
        await held.commit()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)


def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> Any:
    async def call() -> httpx.Response:
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        return await client.post(path, json=body, headers=headers)

    return call


def _move(client: httpx.AsyncClient, order: PhysicalOrder, target: str, line: int = 0) -> Any:
    return _post(
        client, transition_path(order.order_id, order.line_ids[line]), {"target_status": target}
    )


def _hand_over(client: httpx.AsyncClient, order: PhysicalOrder, amount: int) -> Any:
    return _post(client, handover_path(order.order_id), {"amount_cents": amount, "currency": "USD"})


async def _admins(app: FastAPI, db: AsyncSession, count: int) -> list[httpx.AsyncClient]:
    return [(await admin_client(app, db))[0] for _ in range(count)]


async def test_two_administrators_making_one_transition_get_one_200_and_one_409(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["ready_to_ship"])
    async with running_app(make_app) as app:
        clients = await _admins(app, db_session, 2)
        try:
            first, second = await queued(
                db_engine, order.order_id, *(_move(c, order, "shipped") for c in clients)
            )
        finally:
            for client in clients:
                await client.aclose()
    assert (first.status_code, second.status_code) == (200, 409), second.text
    assert (second.json()["code"], second.json()["reason"]) == (
        "INVALID_STATE_TRANSITION",
        "not_a_legal_edge",
    )
    assert await states(db_engine, order.order_id) == ("in_progress", ["shipped"])
    # one line history row, one audit, one notification, one email, no cash
    assert await effects(db_engine, order.order_id) == (1, 1, 1, 1, 0)


async def test_two_administrators_recording_one_handover_record_one_payment(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    async with running_app(make_app) as app:
        clients = await _admins(app, db_session, 2)
        try:
            first, second = await queued(
                db_engine, order.order_id, *(_hand_over(c, order, 1000) for c in clients)
            )
        finally:
            for client in clients:
                await client.aclose()
    assert (first.status_code, second.status_code) == (200, 409), second.text
    assert second.json()["reason"] == "already_recorded"
    assert await states(db_engine, order.order_id) == ("completed", ["delivered"])
    # line + order history, one audit, one notification, one email, one cash payment
    assert await effects(db_engine, order.order_id) == (2, 1, 1, 1, 1)


@pytest.mark.parametrize("first", ["handover", "transition"])
async def test_a_handover_racing_a_transition_on_another_line_has_one_outcome(
    first: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    order = await seed_physical_order(
        db_session, line_states=["shipped", "ready_to_ship"], line_totals=[1200, 800]
    )
    async with running_app(make_app) as app:
        admin_a, admin_b = await _admins(app, db_session, 2)
        try:
            racers = {
                "handover": _hand_over(admin_a, order, 2000),
                "transition": _move(admin_b, order, "shipped", 1),
            }
            names = (
                ["handover", "transition"] if first == "handover" else ["transition", "handover"]
            )
            results = await queued(db_engine, order.order_id, *(racers[n] for n in names))
        finally:
            await admin_a.aclose()
            await admin_b.aclose()
    by_name = dict(zip(names, results, strict=True))
    status, lines = await states(db_engine, order.order_id)
    assert by_name["transition"].status_code == 200, by_name["transition"].text
    if first == "handover":
        assert by_name["handover"].status_code == 409
        assert by_name["handover"].json()["reason"] == "lines_not_ready"
        assert (status, sorted(lines)) == ("in_progress", ["shipped", "shipped"])
        assert (await effects(db_engine, order.order_id))[4] == 0
    else:
        assert by_name["handover"].status_code == 200, by_name["handover"].text
        assert (status, lines) == ("completed", ["delivered", "delivered"])
        assert (await effects(db_engine, order.order_id))[4] == 1


@pytest.mark.parametrize("first", ["reconcile", "transition"])
async def test_a_reconcile_run_racing_a_transition_on_an_unpaid_online_order(
    first: str,
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
) -> None:
    """The provider says paid. Whoever queues first, the payment ends `paid`, and the
    transition moves the line only if it read the payment after reconcile's commit."""
    at = epoch(1971 if first == "reconcile" else 1972)
    seeded = await seed_order(db_session, placed_at=at, physical=True, stl=False)
    await seed_attempt(db_session, seeded, initiated_at=at, mock=mock, state="paid")
    async with db_engine.connect() as conn:
        line_id = await conn.scalar(
            text("SELECT id FROM order_items WHERE order_id = :o"), {"o": seeded.order_id}
        )
    order = PhysicalOrder(seeded.order_id, seeded.user_id, seeded.order_number, (line_id,), "")

    async def reconcile() -> dict[str, int]:
        return await reconcile_stuck(
            factory(db_engine),
            {"mock": mock},
            now=at + timedelta(hours=2),
            start_after=keyset_start(at),
        )

    async with running_app(make_app) as app:
        (client,) = await _admins(app, db_session, 1)
        try:
            transition = _move(client, order, "in_production")
            racers = (reconcile, transition) if first == "reconcile" else (transition, reconcile)
            results = await queued(db_engine, order.order_id, *racers)
        finally:
            await client.aclose()
    counts, response = results if first == "reconcile" else results[::-1]
    async with db_engine.connect() as conn:
        payment = await conn.scalar(
            text("SELECT status FROM payments WHERE order_id = :o"), {"o": order.order_id}
        )
    status, lines = await states(db_engine, order.order_id)
    assert counts["seen"] == 1 and payment == "paid"
    if first == "reconcile":
        assert response.status_code == 200, response.text
        assert (status, lines) == ("in_progress", ["in_production"])
    else:
        assert (response.status_code, response.json()["reason"]) == (409, "payment_required")
        assert (status, lines) == ("in_progress", ["pending"])


async def test_a_reconcile_run_never_waits_on_a_cash_order_being_handed_over(
    make_app: Callable[[], FastAPI],
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
) -> None:
    """A cash order has no online attempt, so the run passes it by while it is locked."""
    at = epoch(1973)
    order = await seed_physical_order(db_session, line_states=["shipped"], placed_at=at)
    async with running_app(make_app) as app:
        (client,) = await _admins(app, db_session, 1)
        try:
            async with order_lock(db_engine, order.order_id) as held:
                handover = asyncio.create_task(_hand_over(client, order, 1000)())
                await wait_for_lock_waiters(db_engine, 1)
                counts = await asyncio.wait_for(
                    reconcile_stuck(
                        factory(db_engine),
                        {"mock": mock},
                        now=at + timedelta(hours=2),
                        start_after=keyset_start(at),
                    ),
                    timeout=RACE_TIMEOUT_SECONDS,
                )
                await held.commit()
            response = await asyncio.wait_for(handover, timeout=RACE_TIMEOUT_SECONDS)
        finally:
            await client.aclose()
    assert counts["seen"] == 0
    assert response.status_code == 200, response.text
    assert await states(db_engine, order.order_id) == ("completed", ["delivered"])


async def test_the_index_alone_refuses_a_second_cash_payment_from_two_unlocked_writers(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Without the order lock both INSERTs overlap; `uq_payments_one_cash` still lets one in."""
    order = await seed_physical_order(db_session, line_states=["shipped"])
    admin = await create_user(db_session, role=UserRole.ADMIN)
    barrier = asyncio.Barrier(2)

    async def write() -> str:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await meet_or_fail(barrier)
            try:
                await insert_cash_payment(
                    session,
                    order_id=order.order_id,
                    amount_cents=1000,
                    currency="USD",
                    recorded_by=admin.id,
                    at=datetime.now(UTC),
                )
            except CashAlreadyRecordedError:
                return "refused"
        return "written"

    outcomes = await asyncio.wait_for(asyncio.gather(write(), write()), RACE_TIMEOUT_SECONDS)
    assert sorted(outcomes) == ["refused", "written"]
    assert (await effects(db_engine, order.order_id))[4] == 1


async def _block_waiters(engine: AsyncEngine, count: int) -> None:
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database()"
                    " AND query ILIKE '%FROM cash_payment_blocks%FOR UPDATE%'"
                )
            )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"fewer than {count} clears ever waited on the block lock")


async def test_two_administrators_clearing_one_block_write_one_audit_row(
    make_app: Callable[[], FastAPI], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    phone = random_phone()
    await seed_block(db_session, buyer.id, phone)
    block_id = await db_session.scalar(
        text("SELECT id FROM cash_payment_blocks WHERE user_id = :u"), {"u": buyer.id}
    )
    path = f"/api/v1/admin/cash-blocks/{block_id}/clear"
    async with running_app(make_app) as app:
        clients = await _admins(app, db_session, 2)
        try:
            async with db_engine.connect() as held:
                await held.execute(
                    text("SELECT id FROM cash_payment_blocks WHERE id = :b FOR UPDATE"),
                    {"b": block_id},
                )
                tasks = [asyncio.create_task(_post(c, path, {})()) for c in clients]
                await _block_waiters(db_engine, 2)
                await held.rollback()
            first, second = await asyncio.wait_for(asyncio.gather(*tasks), RACE_TIMEOUT_SECONDS)
        finally:
            for client in clients:
                await client.aclose()
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json() and first.json()["active"] is False
    async with db_engine.connect() as conn:
        audits = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'cash_block.cleared'"
                " AND entity_id = :b"
            ),
            {"b": block_id},
        )
    assert audits == 1
