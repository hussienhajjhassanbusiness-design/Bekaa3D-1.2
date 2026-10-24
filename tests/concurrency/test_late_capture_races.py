"""R9 (VS-030 plan 6.3): late captures racing on real Postgres leave exactly one live
`late_capture` refund per payment: two provider events (serialised by the `orders` lock),
and the backfill against a live insert (the unique index decides, in either order)."""

import asyncio
import importlib.util
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from app.payments.domain.enums import PaymentProvider, RefundKind
from app.payments.domain.outcome import Outcome
from app.payments.domain.refunds import NewRefund
from app.payments.infrastructure.refunds import SqlRefundStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import late_capture, late_refunds, payment_of

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]
RUNS = 10
RACE_TIMEOUT_SECONDS = 20
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


@pytest.mark.usefixtures("configured_app")
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


def _backfill_module() -> ModuleType:
    path = next(MIGRATIONS.glob("80e56abf0969_*.py"))
    spec = importlib.util.spec_from_file_location("backfill_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _late_without_refund(engine: AsyncEngine) -> NewRefund:
    """A VS-024-era row (late-captured, committed, no refund), and the live sink's refund."""
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        order = await seed_physical_order(db, payment_method="online", payment_status="expired")
        payment_id = await db.scalar(
            text(
                "UPDATE payments SET late_captured_at = now(), captured_amount_cents = 1000,"
                " captured_currency = 'USD' WHERE order_id = :o RETURNING id"
            ),
            {"o": order.order_id},
        )
        await db.commit()
    assert isinstance(payment_id, uuid.UUID)
    return NewRefund(
        order_id=order.order_id,
        payment_id=payment_id,
        provider=PaymentProvider.MOCK,
        kind=RefundKind.LATE_CAPTURE,
        items=(),
        currency="USD",
        reason="late capture: attempt_not_live",
        requested_by=None,
        approved_by=None,
        initiated_at=datetime.now(UTC),
        late_amount_cents=1000,
    )


async def _waiting_insert(engine: AsyncEngine) -> None:
    """Until a second `INSERT INTO refunds` waits on the unique index, or fail."""
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database() AND query ILIKE '%INSERT INTO refunds%'"
                )
            )
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the second insert never waited on the unique index")


async def _live(engine: AsyncEngine, new: NewRefund) -> uuid.UUID | None:
    async with async_sessionmaker(engine)() as session, session.begin():
        return await SqlRefundStore(session).insert_late_capture(new)


async def _backfill(engine: AsyncEngine, module: ModuleType) -> dict[str, int]:
    async with engine.begin() as conn:
        counts: dict[str, int] = await conn.run_sync(module.backfill)
    return counts


async def _race(url: str, *, live_first: bool) -> tuple[uuid.UUID | None, dict[str, int], int]:
    """The first writer holds its uncommitted INSERT until the second waits behind it."""
    engine = create_async_engine(url)
    module = _backfill_module()
    new = await _late_without_refund(engine)
    if live_first:
        async with async_sessionmaker(engine)() as session:
            async with session.begin():
                live_id = await SqlRefundStore(session).insert_late_capture(new)
                task = asyncio.create_task(_backfill(engine, module))
                await _waiting_insert(engine)
            counts = await asyncio.wait_for(task, RACE_TIMEOUT_SECONDS)
    else:
        async with engine.connect() as conn:
            async with conn.begin():
                counts = await conn.run_sync(module.backfill)
                waiter = asyncio.create_task(_live(engine, new))
                await _waiting_insert(engine)
            live_id = await asyncio.wait_for(waiter, RACE_TIMEOUT_SECONDS)
    async with engine.connect() as conn:
        pending = await conn.scalar(
            text("SELECT count(*) FROM refunds WHERE payment_id = :p AND status = 'pending'"),
            {"p": new.payment_id},
        )
    await engine.dispose()
    return live_id, counts, int(pending or 0)


def test_r9_the_backfill_racing_a_live_insert_leaves_one_obligation() -> None:
    """On its own Postgres: the backfill scans every late-captured payment."""
    previous = os.environ.get("DATABASE_URL")
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            url = postgres.get_connection_url()
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            live_id, counts, pending = asyncio.run(_race(url, live_first=True))
            assert live_id is not None and pending == 1
            assert (counts["created"], counts["existing"]) == (0, 1)
            live_id, counts, pending = asyncio.run(_race(url, live_first=False))
            assert live_id is None and pending == 1
            assert counts["created"] == 1
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
