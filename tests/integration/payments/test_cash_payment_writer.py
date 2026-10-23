"""VS-029: `insert_cash_payment` against real PostgreSQL. `uq_payments_one_cash` is the
final guard behind the handover's locks (INV-22): a second cash row is refused by name
inside a SAVEPOINT, so the caller's transaction survives to roll back cleanly."""

from datetime import UTC, datetime
from functools import partial

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.payments.domain.exceptions import CashAlreadyRecordedError
from app.payments.infrastructure.cash_payments import insert_cash_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.fulfillment.order_support import seed_physical_order

pytestmark = pytest.mark.integration


async def test_a_second_cash_payment_is_refused_by_the_index(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    admin = await create_user(db_session, role=UserRole.ADMIN)
    at = datetime.now(UTC)
    insert = partial(
        insert_cash_payment,
        order_id=order.order_id,
        amount_cents=1000,
        currency="USD",
        recorded_by=admin.id,
        at=at,
    )
    async with async_sessionmaker(db_engine)() as session, session.begin():
        first = await insert(session)
        with pytest.raises(CashAlreadyRecordedError):
            await insert(session)
        # The SAVEPOINT absorbed the violation: the transaction is still usable.
        count = await session.scalar(
            text("SELECT count(*) FROM payments WHERE order_id = :o"), {"o": order.order_id}
        )
    assert count == 1
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, provider, status, order_payment_method, verified_at, recorded_by"
                    " FROM payments WHERE order_id = :o"
                ),
                {"o": order.order_id},
            )
        ).one()
    assert (row.id, row.provider, row.status, row.order_payment_method) == (
        first,
        "cash",
        "paid",
        "cash",
    )
    assert (row.verified_at, row.recorded_by) == (at, admin.id)


async def test_other_integrity_errors_are_not_reported_as_already_recorded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """A cash row on an online order breaks a different constraint, which is re-raised."""
    online = await seed_physical_order(db_session, payment_method="online")
    admin = await create_user(db_session, role=UserRole.ADMIN)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        with pytest.raises(IntegrityError) as caught:
            await insert_cash_payment(
                session,
                order_id=online.order_id,
                amount_cents=1000,
                currency="USD",
                recorded_by=admin.id,
                at=datetime.now(UTC),
            )
        await session.rollback()
    assert not isinstance(caught.value, CashAlreadyRecordedError)
    assert "fk_payments_order_payment_method" in str(caught.value)
