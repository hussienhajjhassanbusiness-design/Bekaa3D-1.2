"""VS-030 chargeback races on real Postgres (plan 6.3 R8, R11-R13). Forced orders queue the
racers behind a held `orders` lock. Every run checks invariant M: refunds still to pay or
paid, plus what chargebacks applied, never exceed the paid amount; and no deadlock."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.payments.application.services.chargebacks import record_chargeback
from app.payments.domain.exceptions import ChargebackAllocationInvalidError
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.refund_side import refund_deps
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.test_refund_races import (
    Racer,
    World,
    _id,
    _one,
    money,
    queued,
    together,
)
from tests.integration.deep_support import create_user
from tests.integration.payments.refund_support import Paid, paid_online, payment_of

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
ROUNDS = 5


@pytest.fixture
async def world(db_engine: AsyncEngine, db_session: AsyncSession) -> World:
    return World(db_engine, (await create_user(db_session, role=UserRole.ADMIN)).id)


def charge(
    world: World,
    order: Paid,
    payment: uuid.UUID,
    charged: int,
    items: list[tuple[uuid.UUID, int]],
) -> Racer:
    async def work(session: AsyncSession) -> str:
        try:
            out = await record_chargeback(
                refund_deps(session),
                order_id=order.order_id,
                payment_id=payment,
                dispute_reference=f"dp_{uuid.uuid4().hex}",
                charged_cents=charged,
                items=[ItemFact(i, a) for i, a in items],
                reason="race",
                received_at=datetime.now(UTC),
                ctx=world.ctx,
                at=datetime.now(UTC),
            )
        except ChargebackAllocationInvalidError:
            return "cb_invalid"
        return f"charged:{out.allocation.applied_cents}:{out.allocation.excess_cents}"

    return lambda: world._tx(work)


async def applied(engine: AsyncEngine, order_id: uuid.UUID) -> int:
    row = await _one(
        engine,
        "SELECT COALESCE(SUM(applied_cents), 0) AS a FROM chargebacks WHERE order_id = :o",
        o=order_id,
    )
    return int(row.a)


async def assert_m(engine: AsyncEngine, order_id: uuid.UUID) -> None:
    out, paid = await money(engine, order_id)
    assert out + await applied(engine, order_id) <= paid


async def _order(db: AsyncSession, engine: AsyncEngine) -> tuple[Paid, uuid.UUID]:
    order = await paid_online(db, stl=None)  # one delivered line, 1000 paid
    return order, await payment_of(engine, order.order_id)


async def _status(engine: AsyncEngine, refund: uuid.UUID) -> str:
    row = await _one(engine, "SELECT status::text AS s FROM refunds WHERE id = :r", r=refund)
    return str(row.s)


@pytest.mark.parametrize("first", ["settle", "chargeback"])
async def test_r11_chargeback_racing_settle(
    first: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Paid 1000, a pending 200 goodwill, charged 1000 naming 800 on the line."""
    for _ in range(ROUNDS):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        refund = await _id(await world.create(order.order_id, [(line, 200)])())
        racers = [
            world.action("settle", refund),
            charge(world, order, payment, 1000, [(line, 800)]),
        ]
        results = await queued(
            db_engine, order.order_id, *(racers if first == "settle" else racers[::-1])
        )
        if first == "settle":
            assert results == [f"settle:{refund}", "charged:800:200"]  # settled stays counted
            assert await _status(db_engine, refund) == "settled"
        else:
            assert results == ["charged:1000:0", "refused:not_pending"]  # absorbed
            assert await _status(db_engine, refund) == "voided"
        await assert_m(db_engine, order.order_id)


@pytest.mark.parametrize("first", ["reissue", "chargeback"])
async def test_r12_chargeback_racing_reissue(
    first: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(ROUNDS):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        refund = await _id(await world.create(order.order_id, [(line, 200)])())
        assert await world.action("fail", refund)() == f"fail:{refund}"
        racers = [world.action("reissue", refund), charge(world, order, payment, 1000, [])]
        results = await queued(
            db_engine, order.order_id, *(racers if first == "reissue" else racers[::-1])
        )
        if first == "reissue":
            twin = await _id(results[0])
            assert results[1] == "charged:200:800" and await _status(db_engine, twin) == "voided"
            assert await _status(db_engine, refund) == "failed"  # keeps reissued_at
        else:
            assert results == ["charged:200:800", "refused:not_failed"]
            assert await _status(db_engine, refund) == "voided"
        out, _ = await money(db_engine, order.order_id)
        assert out == 0  # no live obligation remains
        await assert_m(db_engine, order.order_id)


@pytest.mark.parametrize("first", ["create", "chargeback"])
async def test_r13_refund_create_racing_a_chargeback(
    first: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Paid 1000: a create for 600 and a charge of 1000 naming 400 (C1: on top of absorbed)."""
    for _ in range(ROUNDS):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        racers = [
            world.create(order.order_id, [(line, 600)]),
            charge(world, order, payment, 1000, [(line, 400)]),
        ]
        results = await queued(
            db_engine, order.order_id, *(racers if first == "create" else racers[::-1])
        )
        if first == "create":
            assert results[1] == "charged:1000:0"  # the 600 absorbed, then 400 named
        else:
            assert results[0] == "charged:400:600" and results[1].startswith("created:")
        await assert_m(db_engine, order.order_id)


async def test_r8_free_races_of_chargebacks_and_refunds_keep_the_payout_within_paid(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(10):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        results = await together(
            world.create(order.order_id, [(line, 500)]),
            charge(world, order, payment, 700, [(line, 500)]),
            world.create(order.order_id, [(line, 300)]),
        )
        assert all(not r.startswith("db_error") for r in results), results
        await assert_m(db_engine, order.order_id)
