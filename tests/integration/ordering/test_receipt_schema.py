"""VS-029b's constraints on real Postgres (migration 0f43e238eaae, ADR-041): the database
itself refuses the rows the application never writes."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.fulfillment.order_support import seed_physical_order

pytestmark = pytest.mark.integration

_MESSAGE = (
    "INSERT INTO contact_messages (name, email, message, user_id, order_id)"
    " VALUES ('Rana', 'rana@example.com', 'Broken.', :u, :o)"
)


async def _insert(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _stl_line(engine: AsyncEngine, order_id: uuid.UUID) -> uuid.UUID:
    async with engine.connect() as conn:
        line = await conn.scalar(
            text("SELECT id FROM order_items WHERE order_id = :o AND product_type = 'stl'"),
            {"o": order_id},
        )
    assert line is not None
    return uuid.UUID(str(line))


async def test_a_message_linked_to_an_order_needs_a_user(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["delivered"])
    with pytest.raises(IntegrityError, match="ck_contact_messages_order_has_user"):
        await _insert(db_engine, _MESSAGE, u=None, o=order.order_id)
    await _insert(db_engine, _MESSAGE, u=order.user_id, o=order.order_id)
    await _insert(db_engine, _MESSAGE, u=None, o=None)  # a guest's contact form


async def test_a_message_cannot_name_an_unknown_order_or_user(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["delivered"])
    with pytest.raises(IntegrityError, match="fk_contact_messages_order_id"):
        await _insert(db_engine, _MESSAGE, u=order.user_id, o=uuid.uuid4())
    with pytest.raises(IntegrityError, match="fk_contact_messages_user_id"):
        await _insert(db_engine, _MESSAGE, u=uuid.uuid4(), o=None)


@pytest.mark.parametrize("column", ["receipt_confirmed_at", "problem_reported_at"])
async def test_receipt_feedback_is_refused_on_an_stl_line(
    column: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["delivered"],
        stl_line="delivered",
    )
    stl = await _stl_line(db_engine, order.order_id)
    stamp = f"UPDATE order_items SET {column} = now() WHERE id = :i"
    with pytest.raises(IntegrityError, match="ck_order_items_feedback_physical_only"):
        await _insert(db_engine, stamp, i=stl)
    await _insert(db_engine, stamp, i=order.line_ids[0])
