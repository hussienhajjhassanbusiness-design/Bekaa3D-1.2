"""VS-030 races on real Postgres (plan 6.3 R1-R7, R10, R14). Each racer is its own
transaction through the use cases. Forced orders queue the racers behind a held `orders`
lock; free races start them together at a barrier. No run may deadlock."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.fulfillment.application.record_cash_handover import record_cash_handover
from app.fulfillment.application.transition_line import transition_line
from app.fulfillment.infrastructure.delivery_side import (
    SqlDeliveryNotices,
    SqlDeliveryOrders,
    SqlOrderPayments,
)
from app.identity.domain.enums import UserRole
from app.ordering.public import InvalidLineTransitionError, OrderItemStatus
from app.payments.application.services.refunds import (
    AuditContext,
    create_refund,
    fail_refund,
    reissue_refund,
    settle_refund,
    void_refund,
)
from app.payments.domain.enums import RefundKind
from app.payments.domain.exceptions import (
    OrderNotPaidError,
    RefundExceedsAvailableError,
    RefundRefusedError,
)
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.refund_side import refund_deps
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user, csrf, running_app
from tests.integration.fulfillment.delivery_support import admin_client, wait_for_lock_waiters
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import Paid, key, paid_cash, paid_online

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
RACE_TIMEOUT_SECONDS = 20
Racer = Callable[[], Coroutine[Any, Any, str]]


@asynccontextmanager
async def _order_lock(engine: AsyncEngine, order_id: uuid.UUID) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT id FROM orders WHERE id = :o FOR UPDATE"), {"o": order_id})
        try:
            yield conn
        finally:
            await conn.rollback()


async def queued(engine: AsyncEngine, order_id: uuid.UUID, *racers: Racer) -> list[str]:
    """Each racer starts once the previous one waits on the held order lock; Postgres
    then grants the lock in that order, so the first racer listed commits first."""
    async with _order_lock(engine, order_id) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            await wait_for_lock_waiters(engine, n)
        await held.commit()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)


async def together(*racers: Racer) -> list[str]:
    barrier = asyncio.Barrier(len(racers))

    async def run(racer: Racer) -> str:
        await meet_or_fail(barrier)
        return await racer()

    return await asyncio.wait_for(
        asyncio.gather(*(run(r) for r in racers)), timeout=RACE_TIMEOUT_SECONDS
    )


class World:
    def __init__(self, engine: AsyncEngine, admin: uuid.UUID) -> None:
        self.factory = async_sessionmaker(engine, expire_on_commit=False)
        self.ctx = AuditContext(admin)

    async def _tx(self, work: Callable[[AsyncSession], Coroutine[Any, Any, Any]]) -> str:
        try:
            async with self.factory() as session, session.begin():
                result = await work(session)
        except RefundRefusedError as exc:
            return f"refused:{exc.reason}"
        except RefundExceedsAvailableError:
            return "exceeds"
        except OrderNotPaidError:
            return "not_paid"
        except InvalidLineTransitionError as exc:
            return f"line:{exc.reason}"
        return "ok" if result is None else str(result)

    def create(self, order_id: uuid.UUID, items: list[tuple[uuid.UUID, int]]) -> Racer:
        async def work(session: AsyncSession) -> str:
            outcome = await create_refund(
                refund_deps(session),
                order_id=order_id,
                kind=RefundKind.ADMIN,
                items=[ItemFact(i, a) for i, a in items],
                reason="race",
                ctx=self.ctx,
                at=datetime.now(UTC),
            )
            return f"created:{outcome.refund_id}"

        return lambda: self._tx(work)

    def action(self, name: str, refund_id: uuid.UUID) -> Racer:
        async def work(session: AsyncSession) -> str:
            deps, at = refund_deps(session), datetime.now(UTC)
            if name == "settle":
                out = await settle_refund(
                    deps, refund_id=refund_id, reference=None, note=None, ctx=self.ctx, at=at
                )
            elif name == "fail":
                out = await fail_refund(deps, refund_id=refund_id, reason="r", ctx=self.ctx, at=at)
            elif name == "void":
                out = await void_refund(deps, refund_id=refund_id, reason="r", ctx=self.ctx, at=at)
            else:
                out = await reissue_refund(deps, refund_id=refund_id, ctx=self.ctx, at=at)
            return f"{name}:{out.refund_id}" if out.changed else f"{name}:repeat"

        return lambda: self._tx(work)

    def transition(self, order_id: uuid.UUID, item_id: uuid.UUID, target: str) -> Racer:
        async def work(session: AsyncSession) -> str:
            await transition_line(
                SqlDeliveryOrders(session),
                SqlOrderPayments(session),
                SqlAuditWriter(session),
                SqlDeliveryNotices(session),
                order_id=order_id,
                item_id=item_id,
                target=OrderItemStatus(target),
                admin_id=self.ctx.actor_user_id,
                at=datetime.now(UTC),
                note=None,
                request_id=None,
                ip_hash=None,
            )
            return f"moved:{target}"

        return lambda: self._tx(work)

    def handover(self, order_id: uuid.UUID, amount: int) -> Racer:
        async def work(session: AsyncSession) -> str:
            await record_cash_handover(
                SqlDeliveryOrders(session),
                SqlOrderPayments(session),
                SqlAuditWriter(session),
                SqlDeliveryNotices(session),
                order_id=order_id,
                amount_cents=amount,
                currency="USD",
                admin_id=self.ctx.actor_user_id,
                at=datetime.now(UTC),
                note=None,
                request_id=None,
                ip_hash=None,
            )
            return "handed_over"

        return lambda: self._tx(work)


@pytest.fixture
async def world(db_engine: AsyncEngine, db_session: AsyncSession) -> World:
    return World(db_engine, (await create_user(db_session, role=UserRole.ADMIN)).id)


async def _one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def money(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[int, int]:
    """Invariant M: (pending + settled + owed on the paid payment, the paid amount)."""
    row = await _one(
        engine,
        "SELECT COALESCE(SUM(r.amount_cents) FILTER (WHERE r.status IN ('pending', 'settled')"
        " OR (r.status = 'failed' AND r.reissued_at IS NULL)), 0) AS out, p.amount_cents AS paid"
        " FROM payments p LEFT JOIN refunds r ON r.payment_id = p.id"
        " WHERE p.order_id = :o AND p.status IN ('paid', 'partially_refunded', 'refunded')"
        " GROUP BY p.amount_cents",
        o=order_id,
    )
    return int(row.out), int(row.paid)


async def _id(result: str) -> uuid.UUID:
    return uuid.UUID(result.split(":", 1)[1])


# --- R1, R2 -------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["online", "cash"])
async def test_r1_concurrent_partials_never_exceed_the_paid_amount(
    method: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(20):
        order: Paid = (
            await paid_online(db_session, stl=None)
            if method == "online"
            else await paid_cash(db_session)
        )
        line = order.physical[0]
        results = await together(*(world.create(order.order_id, [(line, 400)]) for _ in range(3)))
        assert sorted(r.split(":")[0] for r in results) == ["created", "created", "exceeds"]
        out, paid = await money(db_engine, order.order_id)
        assert out == 800 <= paid


async def test_r2_two_partials_that_sum_to_the_total_both_succeed(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(10):
        order = await paid_online(db_session, stl=None)
        line = order.physical[0]
        results = await together(
            world.create(order.order_id, [(line, 600)]), world.create(order.order_id, [(line, 400)])
        )
        assert all(r.startswith("created") for r in results)
        row = await _one(
            db_engine,
            "SELECT o.status::text AS o, i.fulfillment_status::text AS i FROM orders o"
            " JOIN order_items i ON i.order_id = o.id WHERE o.id = :o",
            o=order.order_id,
        )
        assert (row.o, row.i) == ("refunded", "refunded")


# --- R3 -----------------------------------------------------------------------------------


async def test_r3_the_same_idempotency_key_in_parallel_makes_one_refund(
    db_engine: AsyncEngine, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    order = await paid_online(db_session, stl=None)
    async with running_app(make_app) as app:
        client, _ = await admin_client(app, db_session)
        try:
            idem = key()
            body = {
                "items": [{"order_item_id": str(order.physical[0]), "amount_cents": 100}],
                "reason": "Parallel key.",
            }
            path = f"/api/v1/admin/orders/{order.order_id}/refunds"
            headers = csrf(client) | {"Idempotency-Key": idem}
            barrier = asyncio.Barrier(2)

            async def post() -> Any:
                await meet_or_fail(barrier)
                return await client.post(path, json=body, headers=headers)

            first, second = await asyncio.gather(post(), post())
        finally:
            await client.aclose()
    codes = sorted([first.status_code, second.status_code])
    assert codes in ([201, 201], [201, 409]), (first.text, second.text)
    if codes == [201, 201]:
        assert first.json() == second.json()
    row = await _one(
        db_engine, "SELECT count(*) AS n FROM refunds WHERE order_id = :o", o=order.order_id
    )
    assert row.n == 1


# --- R4, R5, R10 --------------------------------------------------------------------------


@pytest.mark.parametrize("refund_first", [True, False])
async def test_r4_a_full_stl_refund_racing_its_delivery(
    refund_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(5):
        order = await paid_online(db_session, physical=("delivered",))
        assert order.stl is not None
        refund = world.create(order.order_id, [(order.stl, 500)])
        deliver = world.transition(order.order_id, order.stl, "delivered")
        racers = (refund, deliver) if refund_first else (deliver, refund)
        results = await queued(db_engine, order.order_id, *racers)
        first, second = results if refund_first else results[::-1]
        assert first.startswith("created")
        assert second == ("line:line_closed" if refund_first else "moved:delivered")
        state = await _one(
            db_engine,
            "SELECT fulfillment_status::text AS s FROM order_items WHERE id = :i",
            i=order.stl,
        )
        assert state.s == "refunded"


@pytest.mark.parametrize("refund_first", [True, False])
async def test_r5_a_refund_racing_the_cash_handover(
    refund_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(5):
        order = await seed_physical_order(
            db_session,
            payment_method="cash",
            fulfillment="pickup",
            line_states=("ready_for_pickup",),
        )
        refund = world.create(order.order_id, [(order.line_ids[0], 300)])
        handover = world.handover(order.order_id, 1000)
        racers = (refund, handover) if refund_first else (handover, refund)
        results = await queued(db_engine, order.order_id, *racers)
        got = dict(
            zip(
                ("refund", "handover") if refund_first else ("handover", "refund"),
                results,
                strict=True,
            )
        )
        assert got["handover"] == "handed_over"
        assert got["refund"] == "not_paid" if refund_first else got["refund"].startswith("created")
        count = await _one(
            db_engine, "SELECT count(*) AS n FROM refunds WHERE order_id = :o", o=order.order_id
        )
        assert count.n == (0 if refund_first else 1)


@pytest.mark.parametrize("refund_first", [True, False])
async def test_r10_a_refund_racing_a_transition_on_another_line(
    refund_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(5):
        order = await paid_online(db_session, stl=None, physical=("delivered", "in_production"))
        done, busy = order.physical
        refund = world.create(order.order_id, [(done, 1000)])
        move = world.transition(order.order_id, busy, "ready_to_ship")
        results = await queued(
            db_engine, order.order_id, *((refund, move) if refund_first else (move, refund))
        )
        assert {r.split(":")[0] for r in results} == {"created", "moved"}
        row = await _one(
            db_engine,
            "SELECT o.status::text AS o, array_agg(i.fulfillment_status::text ORDER BY i.id) AS s"
            " FROM orders o JOIN order_items i ON i.order_id = o.id"
            " WHERE o.id = :o GROUP BY o.status",
            o=order.order_id,
        )
        expected = sorted(["refunded", "ready_to_ship"])
        assert (row.o, sorted(row.s)) == ("partially_refunded", expected)


# --- R6, R7, R14 --------------------------------------------------------------------------


async def _pending(
    world: World, db_session: AsyncSession, amount: int = 300
) -> tuple[Paid, uuid.UUID]:
    order = await paid_online(db_session, stl=None)
    created = await world.create(order.order_id, [(order.physical[0], amount)])()
    return order, await _id(created)


@pytest.mark.parametrize(("a", "b"), [("settle", "fail"), ("fail", "settle")])
async def test_r6_settle_racing_fail_has_one_winner(
    a: str, b: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(5):
        order, refund = await _pending(world, db_session)
        first, second = await queued(
            db_engine, order.order_id, world.action(a, refund), world.action(b, refund)
        )
        assert first == f"{a}:{refund}"
        assert second == "refused:not_pending"
        row = await _one(db_engine, "SELECT status::text AS s FROM refunds WHERE id = :r", r=refund)
        assert row.s == {"settle": "settled", "fail": "failed"}[a]


async def test_r7_two_concurrent_reissues_make_one_refund(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(10):
        order, refund = await _pending(world, db_session)
        assert (await world.action("fail", refund)()) == f"fail:{refund}"
        results = await together(world.action("reissue", refund), world.action("reissue", refund))
        assert sorted(r.split(":")[0] for r in results) == ["refused", "reissue"]
        assert "refused:already_reissued" in results
        row = await _one(
            db_engine, "SELECT count(*) AS n FROM refunds WHERE reissue_of_refund_id = :r", r=refund
        )
        assert row.n == 1
        out, paid = await money(db_engine, order.order_id)
        assert out == 300 <= paid


@pytest.mark.parametrize(("a", "b"), [("void", "settle"), ("settle", "void")])
async def test_r14_void_racing_settle_has_one_winner(
    a: str, b: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(5):
        order, refund = await _pending(world, db_session)
        first, second = await queued(
            db_engine, order.order_id, world.action(a, refund), world.action(b, refund)
        )
        assert first == f"{a}:{refund}"
        assert second == ("refused:not_pending" if a == "void" else "refused:already_settled")
        row = await _one(
            db_engine,
            "SELECT status::text AS s, settled_at IS NOT NULL AS settled,"
            " voided_at IS NOT NULL AS voided FROM refunds WHERE id = :r",
            r=refund,
        )
        assert not (row.settled and row.voided)
        assert row.s == {"void": "voided", "settle": "settled"}[a]
