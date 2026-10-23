"""R9 (VS-030 plan 6.3): late captures racing on real Postgres leave exactly one live
`late_capture` refund per payment. Two provider events meet at a barrier; the `orders`
lock serialises them and the second sees `late_captured_at`."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.payments.domain.outcome import Outcome
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import late_capture, late_refunds, payment_of

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
RUNS = 10
RACE_TIMEOUT_SECONDS = 20


@pytest.mark.parametrize("run", range(RUNS))
async def test_r9_two_provider_events_leave_one_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession, run: int
) -> None:
    order = await seed_physical_order(db_session, payment_method="online", payment_status="expired")
    payment_id = await payment_of(db_engine, order.order_id)
    barrier = asyncio.Barrier(2)

    async def event() -> Outcome:
        await meet_or_fail(barrier)
        return await late_capture(db_engine, payment_id, 1000)

    outcomes = await asyncio.wait_for(
        asyncio.gather(event(), event()), timeout=RACE_TIMEOUT_SECONDS
    )
    assert sorted(outcomes) == sorted([Outcome.LATE_CAPTURE, Outcome.NOOP])
    (row,) = await late_refunds(db_engine, payment_id)
    assert (row.status, row.amount_cents) == ("pending", 1000)
