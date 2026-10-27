"""VS-043 Payments reads on real Postgres (plan 6.2 R16): `refunded_cents_by_line`,
`refund_covered_lines` and `unsettled_refund_exists` against VS-030 plan 3.7, `is_counted` and
BR-126, over every (kind, status, reissued) combination."""

import uuid
from datetime import UTC, datetime
from itertools import product

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.payments.domain.enums import RefundKind, RefundStatus
from app.payments.domain.refunds import RefundFact, is_counted
from app.payments.public import (
    refund_covered_lines,
    refunded_cents_by_line,
    unsettled_refund_exists,
)
from tests.integration.deep_support import create_user
from tests.integration.payments.refund_support import Paid, paid_online, payment_of

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

COMBINATIONS = [
    (kind, status, reissued)
    for kind, status, reissued in product(RefundKind, RefundStatus, (False, True))
    if not reissued or status is RefundStatus.FAILED
]


async def _refund(
    db: AsyncSession,
    order: Paid,
    payment_id: uuid.UUID,
    *,
    kind: str = "admin",
    status: str = "pending",
    reissued: bool = False,
    cents: int = 300,
) -> uuid.UUID:
    """One refund with one item on the order's first line, in any state, written directly."""
    at = datetime.now(UTC)
    refund_id: uuid.UUID = (
        await db.execute(
            text(
                "INSERT INTO refunds (order_id, payment_id, payment_provider, kind, status,"
                " amount_cents, reason, requested_by, initiated_at, settled_at, failed_at,"
                " voided_at, void_reason, reissued_at)"
                " VALUES (:o, :p, 'mock', CAST(:k AS refund_kind), CAST(:s AS refund_status),"
                " :a, 'test', :by, :at, :settled, :failed, :voided, :vr, :re) RETURNING id"
            ),
            {
                "o": order.order_id,
                "p": payment_id,
                "k": kind,
                "s": status,
                "a": cents,
                "by": None if kind == "late_capture" else order.user_id,
                "at": at,
                "settled": at if status == "settled" else None,
                "failed": at if status == "failed" else None,
                "voided": at if status == "voided" else None,
                "vr": "test" if status == "voided" else None,
                "re": at if reissued else None,
            },
        )
    ).scalar_one()
    await db.execute(
        text(
            "INSERT INTO refund_items (refund_id, order_id, order_item_id, amount_cents)"
            " VALUES (:r, :o, :i, :a)"
        ),
        {"r": refund_id, "o": order.order_id, "i": order.physical[0], "a": cents},
    )
    await db.commit()
    return refund_id


async def _chargeback(db: AsyncSession, order: Paid, payment_id: uuid.UUID, cents: int) -> None:
    admin = (await create_user(db)).id
    chargeback_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO chargebacks (id, order_id, payment_id, payment_provider,"
            " provider_dispute_reference, charged_cents, applied_cents, excess_cents, reason,"
            " recorded_by, received_at)"
            " VALUES (:id, :o, :p, 'mock', :ref, :c, :c, 0, 'test', :by, now())"
        ),
        {
            "id": chargeback_id,
            "o": order.order_id,
            "p": payment_id,
            "ref": f"dp_{uuid.uuid4().hex}",
            "c": cents,
            "by": admin,
        },
    )
    await db.execute(
        text(
            "INSERT INTO chargeback_items (chargeback_id, order_id, order_item_id, amount_cents)"
            " VALUES (:cb, :o, :i, :a)"
        ),
        {"cb": chargeback_id, "o": order.order_id, "i": order.physical[0], "a": cents},
    )
    await db.commit()


async def _reads(engine: AsyncEngine, line_id: uuid.UUID) -> tuple[int, bool]:
    async with async_sessionmaker(engine)() as session:
        refunded = await refunded_cents_by_line(session, [line_id])
        covered = await refund_covered_lines(session, [line_id])
    return refunded.get(line_id, 0), line_id in covered


@pytest.mark.parametrize(("kind", "status", "reissued"), COMBINATIONS)
async def test_r16_the_sql_reads_match_plan_3_7_and_is_counted(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    kind: RefundKind,
    status: RefundStatus,
    reissued: bool,
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    await _refund(db_session, order, payment, kind=kind, status=status, reissued=reissued)
    refunded, covered = await _reads(db_engine, order.physical[0])
    counts_for_revenue = kind is not RefundKind.LATE_CAPTURE and status in {
        RefundStatus.PENDING,
        RefundStatus.SETTLED,
    }
    assert refunded == (300 if counts_for_revenue else 0)
    fact = RefundFact(uuid.uuid4(), payment, kind, status, reissued, 300)
    assert covered is is_counted(fact)
    unsettled = status is RefundStatus.PENDING or (status is RefundStatus.FAILED and not reissued)
    async with async_sessionmaker(db_engine)() as session:
        assert await unsettled_refund_exists(session, order.user_id) is unsettled


async def test_chargeback_items_count_and_cover_and_add_to_refunds(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    await _refund(db_session, order, payment, status="settled", cents=200)
    await _chargeback(db_session, order, payment, 500)
    assert await _reads(db_engine, order.physical[0]) == (700, True)


async def test_a_line_nothing_counts_against_reads_zero_and_uncovered(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    assert await _reads(db_engine, order.physical[0]) == (0, False)
    async with async_sessionmaker(db_engine)() as session:
        assert await refunded_cents_by_line(session, []) == {}
        assert await refund_covered_lines(session, []) == frozenset()


async def test_unsettled_refund_exists_cases(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Pending and owed block; a failed refund whose reissue settled, a voided one, a settled
    late capture, another user's refund and no orders at all do not (BR-126)."""

    async def unsettled(user_id: uuid.UUID) -> bool:
        async with async_sessionmaker(db_engine)() as session:
            return await unsettled_refund_exists(session, user_id)

    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    failed = await _refund(db_session, order, payment, status="failed", reissued=True)
    reissue = await _refund(db_session, order, payment, status="settled")
    await db_session.execute(
        text("UPDATE refunds SET reissue_of_refund_id = :f WHERE id = :r"),
        {"f": failed, "r": reissue},
    )
    await _refund(db_session, order, payment, status="voided")
    await _refund(db_session, order, payment, kind="late_capture", status="settled")
    await db_session.commit()
    assert not await unsettled(order.user_id)

    other = await paid_online(db_session, stl=None)
    await _refund(db_session, other, await payment_of(db_engine, other.order_id))
    assert not await unsettled(order.user_id)
    assert await unsettled(other.user_id)

    # One live late capture per payment (`uq_refunds_one_live_late_capture`): a second order.
    late = await paid_online(db_session, stl=None)
    late_payment = await payment_of(db_engine, late.order_id)
    await _refund(db_session, late, late_payment, kind="late_capture", status="pending")
    assert await unsettled(late.user_id)

    owed = await paid_online(db_session, stl=None)
    await _refund(db_session, owed, await payment_of(db_engine, owed.order_id), status="failed")
    assert await unsettled(owed.user_id)

    assert not await unsettled((await create_user(db_session)).id)
