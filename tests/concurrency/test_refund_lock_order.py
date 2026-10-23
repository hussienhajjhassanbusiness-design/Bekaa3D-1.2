"""LO2 and LO3 (VS-030 plan 6.4): the SQL each refund path runs takes its locks in rank
order (orders < order_items < payments < refunds), and a random mixed workload of
refunds, settles, fails, voids, reissues and transitions never deadlocks."""

import asyncio
import random
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.test_refund_races import World
from tests.integration.deep_support import create_user
from tests.integration.payments.refund_support import Paid, paid_online

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]

# A statement that takes (or waits for) a row lock, and its rank (plan 8.1).
RANKS = [
    (re.compile(r"FROM orders\b.*FOR UPDATE", re.S), 1, "orders FOR UPDATE"),
    (re.compile(r"FROM order_items\b.*FOR UPDATE", re.S), 2, "order_items FOR UPDATE ORDER BY id"),
    (re.compile(r"FROM payments\b.*FOR UPDATE", re.S), 3, "payments FOR UPDATE ORDER BY id"),
    (re.compile(r"FROM refunds\b.*FOR UPDATE", re.S), 4, "refunds FOR UPDATE"),
    (re.compile(r"^\s*INSERT INTO refunds\b", re.S), 4, "INSERT refunds"),
    (re.compile(r"^\s*INSERT INTO refund_items\b", re.S), 4, "INSERT refund_items"),
    (re.compile(r"^\s*UPDATE refunds\b", re.S), 4, "UPDATE refunds (held)"),
    (re.compile(r"^\s*UPDATE order_items\b", re.S), 2, "UPDATE order_items (held)"),
    (re.compile(r"^\s*UPDATE payments\b", re.S), 3, "UPDATE payments (held)"),
    (re.compile(r"^\s*UPDATE orders\b", re.S), 1, "UPDATE orders (held)"),
]


@contextmanager
def recorded(engine: AsyncEngine) -> Iterator[list[str]]:
    statements: list[str] = []

    def listen(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", listen)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listen)


def lock_trace(statements: list[str]) -> list[tuple[int, str]]:
    trace = []
    for statement in statements:
        for pattern, rank, label in RANKS:
            if pattern.search(statement):
                trace.append((rank, label))
                break
    return trace


def acquisitions(trace: list[tuple[int, str]]) -> list[int]:
    """The ranks of the locks first taken: writes to rows already held add no new lock."""
    return [rank for rank, label in trace if "(held)" not in label]


@pytest.fixture
async def world(db_engine: AsyncEngine, db_session: AsyncSession) -> World:
    return World(db_engine, (await create_user(db_session, role=UserRole.ADMIN)).id)


async def test_lo2_every_refund_path_locks_in_rank_order(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    traces: dict[str, list[tuple[int, str]]] = {}

    async def path(name: str, racer: Any) -> str:
        with recorded(db_engine) as statements:
            result: str = await racer()
        traces[name] = lock_trace(statements)
        return result

    created = await path("create", world.create(order.order_id, [(a, 300)]))
    refund = uuid.UUID(created.split(":", 1)[1])
    await path("settle", world.action("settle", refund))
    second = uuid.UUID((await world.create(order.order_id, [(b, 200)])()).split(":", 1)[1])
    await path("fail", world.action("fail", second))
    await path("reissue", world.action("reissue", second))
    third = uuid.UUID((await world.create(order.order_id, [(b, 100)])()).split(":", 1)[1])
    await path("void", world.action("void", third))
    for name, trace in traces.items():
        ranks = acquisitions(trace)
        print(f"LO2 {name}: " + " -> ".join(label for _, label in trace))
        assert ranks == sorted(ranks), (name, trace)
        assert ranks[:3] == [1, 2, 3], (name, trace)


async def test_lo3_a_random_mixed_workload_never_deadlocks(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    orders: list[Paid] = [
        await paid_online(db_session, physical=("pending", "delivered")) for _ in range(3)
    ]
    refunds: list[uuid.UUID] = []
    rng = random.Random(30)
    outcomes: dict[str, int] = {}

    async def one() -> None:
        order = rng.choice(orders)
        kind = rng.choice(["create", "create", "settle", "fail", "void", "reissue", "move", "stl"])
        if kind == "create":
            line = rng.choice([order.physical[1], order.stl])
            assert line is not None
            racer = world.create(order.order_id, [(line, rng.randint(1, 60))])
        elif kind == "move":
            states = ["in_production", "ready_to_ship", "shipped", "delivered"]
            racer = world.transition(order.order_id, order.physical[0], rng.choice(states))
        elif kind == "stl":
            assert order.stl is not None
            racer = world.transition(order.order_id, order.stl, "delivered")
        elif refunds:
            racer = world.action(kind, rng.choice(refunds))
        else:
            return
        try:
            result = await racer()
        except DBAPIError as exc:  # only a deadlock may fail this test
            assert "deadlock" not in str(exc).lower(), exc
            result = "db_error"
        if result.startswith("created:"):
            refunds.append(uuid.UUID(result.split(":", 1)[1]))
        outcomes[result.split(":")[0]] = outcomes.get(result.split(":")[0], 0) + 1

    async def worker(n: int) -> None:
        for _ in range(n):
            await one()

    await asyncio.wait_for(asyncio.gather(*(worker(50) for _ in range(4))), timeout=240)
    print("LO3 outcomes:", dict(sorted(outcomes.items())))
    assert sum(outcomes.values()) >= 150
    async with db_engine.connect() as conn:
        for order in orders:
            row = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(SUM(r.amount_cents) FILTER (WHERE r.status IN"
                        " ('pending', 'settled')"
                        " OR (r.status = 'failed' AND r.reissued_at IS NULL)), 0) AS out,"
                        " p.amount_cents AS paid FROM payments p"
                        " LEFT JOIN refunds r ON r.payment_id = p.id WHERE p.order_id = :o"
                        " GROUP BY p.amount_cents"
                    ),
                    {"o": order.order_id},
                )
            ).one()
            assert row.out <= row.paid
