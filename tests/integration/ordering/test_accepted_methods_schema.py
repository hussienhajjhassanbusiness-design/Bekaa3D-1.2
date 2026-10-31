"""INV-25 (VS-049, ADR-048): PostgreSQL itself refuses an order line whose snapshot does not
accept the order's payment method, or a snapshot on the wrong product type."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.test_refund_schema import assert_refused, drop_constraint

pytestmark = pytest.mark.integration

BY_TYPE = "ck_order_items_accepted_methods_by_type"
ACCEPTED = "ck_order_items_method_accepted"
SET_SNAPSHOT = (
    "UPDATE order_items SET accepted_payment_methods_snapshot ="
    " CAST(:v AS accepted_payment_methods) WHERE id = :i"
)


async def _stl_line_id(engine: AsyncEngine, order_id: uuid.UUID) -> uuid.UUID:
    sql = "SELECT id FROM order_items WHERE order_id = :o AND product_type = 'stl'"
    async with engine.connect() as conn:
        line_id: uuid.UUID = (await conn.execute(text(sql), {"o": order_id})).scalar_one()
    return line_id


@pytest.mark.parametrize(("payment_method", "refused"), [("cash", "online"), ("online", "cash")])
async def test_a_physical_line_cannot_snapshot_a_set_without_its_orders_method(
    db_engine: AsyncEngine, db_session: AsyncSession, payment_method: str, refused: str
) -> None:
    order = await seed_physical_order(db_session, payment_method=payment_method)
    params = {"v": refused, "i": order.line_ids[0]}
    await assert_refused(
        db_engine, ACCEPTED, SET_SNAPSHOT, params, drop=drop_constraint("order_items", ACCEPTED)
    )


@pytest.mark.parametrize("payment_method", ["cash", "online"])
async def test_a_physical_line_may_snapshot_its_own_method_or_both(
    db_engine: AsyncEngine, db_session: AsyncSession, payment_method: str
) -> None:
    order = await seed_physical_order(db_session, payment_method=payment_method)
    async with db_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            for value in (payment_method, "online_or_cash"):
                await conn.execute(text(SET_SNAPSHOT), {"v": value, "i": order.line_ids[0]})
        finally:
            await transaction.rollback()


async def test_a_physical_line_must_snapshot_what_its_product_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session)
    params = {"v": None, "i": order.line_ids[0]}
    await assert_refused(
        db_engine, BY_TYPE, SET_SNAPSHOT, params, drop=drop_constraint("order_items", BY_TYPE)
    )


@pytest.mark.parametrize("value", ["online", "online_or_cash"])
async def test_an_stl_line_snapshots_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, value: str
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", stl_line="awaiting_delivery"
    )
    params = {"v": value, "i": await _stl_line_id(db_engine, order.order_id)}
    await assert_refused(
        db_engine, BY_TYPE, SET_SNAPSHOT, params, drop=drop_constraint("order_items", BY_TYPE)
    )
