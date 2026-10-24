"""VS-030 chargeback races on real Postgres (plan 6.3 R8, R11-R13). Forced orders queue the
racers behind a held `orders` lock. Invariant M: refunds still to pay or paid, plus what
chargebacks applied, never exceed the paid amount, and excess exists only at zero balance."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.application.ports import PaymentProviderPort
from app.payments.application.services.chargebacks import record_chargeback
from app.payments.domain.exceptions import (
    CaptureRecordRefusedError,
    ChargebackAllocationInvalidError,
    ChargebackDuplicateError,
)
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.manual import record_capture_manually
from app.payments.infrastructure.refund_side import refund_deps
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.concurrency.test_refund_races import (
    Racer,
    World,
    _id,
    _one,
    money,
    queued,
    together,
)
from tests.integration.deep_support import create_user, csrf, running_app
from tests.integration.fulfillment.delivery_support import admin_client
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import (
    Paid,
    key,
    late_refunds,
    paid_online,
    payment_of,
)
from tests.integration.payments.test_verification_recovery import NoStatus

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
    dispute: str | None = None,
) -> Racer:
    async def work(session: AsyncSession) -> str:
        out = await record_chargeback(
            refund_deps(session),
            order_id=order.order_id,
            payment_id=payment,
            dispute_reference=dispute or f"dp_{uuid.uuid4().hex}",
            charged_cents=charged,
            items=[ItemFact(i, a) for i, a in items],
            reason="race",
            received_at=datetime.now(UTC),
            ctx=world.ctx,
            at=datetime.now(UTC),
        )
        return f"charged:{out.allocation.applied_cents}:{out.allocation.excess_cents}"

    async def run() -> str:
        """Refusals escape the transaction, as in the route, so a loser writes nothing."""
        try:
            return await world._tx(work)
        except ChargebackAllocationInvalidError:
            return "cb_invalid"
        except ChargebackDuplicateError:
            return "duplicate"

    return run


async def charged(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[int, int]:
    """(applied, excess) over the order's chargebacks."""
    row = await _one(
        engine,
        "SELECT COALESCE(SUM(applied_cents), 0) AS a, COALESCE(SUM(excess_cents), 0) AS x"
        " FROM chargebacks WHERE order_id = :o",
        o=order_id,
    )
    return int(row.a), int(row.x)


async def assert_m(engine: AsyncEngine, order_id: uuid.UUID) -> None:
    out, paid = await money(engine, order_id)
    applied, excess = await charged(engine, order_id)
    assert out + applied <= paid
    if excess:  # the bank took more only once nothing was left to refund
        assert out + applied == paid


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
        racers = [
            world.action("reissue", refund),
            charge(world, order, payment, 1000, [(line, 800)]),
        ]
        results = await queued(
            db_engine, order.order_id, *(racers if first == "reissue" else racers[::-1])
        )
        if first == "reissue":
            twin = await _id(results[0])
            assert results[1] == "charged:1000:0" and await _status(db_engine, twin) == "voided"
            assert await _status(db_engine, refund) == "failed"  # keeps reissued_at
        else:
            assert results == ["charged:1000:0", "refused:not_failed"]
            assert await _status(db_engine, refund) == "voided"
        out, _ = await money(db_engine, order.order_id)
        assert out == 0  # no live obligation remains
        await assert_m(db_engine, order.order_id)


@pytest.mark.parametrize("first", ["create", "chargeback"])
async def test_r13_refund_create_racing_a_chargeback(
    first: str, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Paid 1000: a create for 600 and a charge of 1000 naming the whole line. Whichever
    commits second is refused: the items must cover exactly what is still refundable."""
    for _ in range(ROUNDS):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        racers = [
            world.create(order.order_id, [(line, 600)]),
            charge(world, order, payment, 1000, [(line, 1000)]),
        ]
        results = await queued(
            db_engine, order.order_id, *(racers if first == "create" else racers[::-1])
        )
        if first == "create":
            assert results[0].startswith("created:") and results[1] == "cb_invalid"
        else:
            assert results == ["charged:1000:0", "exceeds"]
        await assert_m(db_engine, order.order_id)


async def test_r8_free_races_of_chargebacks_and_refunds_keep_the_payout_within_paid(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Free order: the charge writes when it commits first, else its exact total is wrong
    (the creates it would absorb moved it) and it is refused; R13 forces both orders."""
    for _ in range(10):
        order, payment = await _order(db_session, db_engine)
        line = order.physical[0]
        results = await together(
            world.create(order.order_id, [(line, 500)]),
            charge(world, order, payment, 200, [(line, 200)]),
            world.create(order.order_id, [(line, 300)]),
        )
        assert results[1] in ("charged:200:0", "cb_invalid"), results
        assert all(not r.startswith("db_error") for r in results), results
        await assert_m(db_engine, order.order_id)


async def test_one_dispute_reference_on_two_orders_in_parallel_records_one(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The loser's 409 rolls back its voids: its goodwill refund is still payable."""
    for _ in range(ROUNDS):
        orders = [await _order(db_session, db_engine) for _ in range(2)]
        refunds = [
            await _id(await world.create(o.order_id, [(o.physical[0], 200)])()) for o, _ in orders
        ]
        dispute = f"dp_shared_{uuid.uuid4().hex}"
        results = await together(
            *(charge(world, o, p, 1000, [(o.physical[0], 800)], dispute) for o, p in orders)
        )
        assert sorted(results) == ["charged:1000:0", "duplicate"]
        loser = results.index("duplicate")
        assert await _status(db_engine, refunds[loser]) == "pending"
        assert await _status(db_engine, refunds[1 - loser]) == "voided"
        row = await _one(
            db_engine,
            "SELECT count(*) AS n FROM chargebacks WHERE provider_dispute_reference = :d",
            d=dispute,
        )
        assert row.n == 1


async def test_the_same_key_twice_in_parallel_records_one_chargeback(
    db_engine: AsyncEngine, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    order, payment = await _order(db_session, db_engine)
    async with running_app(make_app) as app:
        client, _ = await admin_client(app, db_session)
        try:
            body = {
                "payment_id": str(payment),
                "provider_dispute_reference": f"dp_{uuid.uuid4().hex}",
                "charged_cents": 1000,
                "items": [{"order_item_id": str(order.physical[0]), "amount_cents": 1000}],
                "reason": "Parallel key.",
                "received_at": "2026-10-20T10:00:00Z",
            }
            path = f"/api/v1/admin/orders/{order.order_id}/chargebacks"
            headers = csrf(client) | {"Idempotency-Key": key()}
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
    else:
        loser = first if first.status_code == 409 else second
        assert loser.json()["code"] == "IDEMPOTENCY_REQUEST_IN_PROGRESS", loser.text
    row = await _one(
        db_engine, "SELECT count(*) AS n FROM chargebacks WHERE order_id = :o", o=order.order_id
    )
    assert row.n == 1


async def test_two_record_captures_in_parallel_leave_one_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(ROUNDS):
        order = await seed_physical_order(
            db_session, payment_method="online", payment_status="expired"
        )
        payment = await payment_of(db_engine, order.order_id)
        admin = (await create_user(db_session, role=UserRole.ADMIN)).id
        results = await together(
            partial(_record, db_engine, payment, admin, 1200),
            partial(_record, db_engine, payment, admin, 1300),
        )
        assert sorted(results) == ["late_capture", "refused:already_late_captured"]
        assert len(await late_refunds(db_engine, payment)) == 1


async def _record(engine: AsyncEngine, payment: uuid.UUID, admin: uuid.UUID, amount: int) -> str:
    providers = {"mock": cast(PaymentProviderPort, NoStatus())}
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            outcome = await record_capture_manually(
                session,
                providers,
                payment,
                admin_id=admin,
                amount_cents=amount,
                currency="USD",
                dashboard_reference="dash",
                reason="dashboard shows a capture",
            )
    except CaptureRecordRefusedError as exc:
        return f"refused:{exc.refusal}"
    return str(outcome)
