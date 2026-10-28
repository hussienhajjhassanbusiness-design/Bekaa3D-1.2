"""VS-045 (0b349a492461, ADR-047): only an anonymised order may lack its phone and address, an
anonymised one holds no personal field and is closed. The database refuses the bad row itself."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.fulfillment.order_support import seed_physical_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

_SCRUB = (
    "recipient_name = NULL, contact_phone_snapshot = NULL,"
    " city = NULL, area = NULL, street = NULL, landmark_notes = NULL, customer_note = NULL"
)


async def _try(engine: AsyncEngine, sql: str, order_id: object) -> None:
    async with engine.connect() as conn:
        await conn.execute(text(f"UPDATE orders SET {sql} WHERE id = :o"), {"o": order_id})
        await conn.rollback()


@pytest.mark.parametrize(
    ("assignments", "constraint"),
    [
        pytest.param(
            "contact_phone_snapshot = NULL, contact_phone_hash = NULL",
            "ck_orders_physical_has_phone",
            id="live_order_without_phone",
        ),
        pytest.param("recipient_name = NULL", "ck_orders_delivery_address", id="live_no_name"),
        pytest.param("anonymized_at = now()", "ck_orders_anonymised_shape", id="keeps_pii"),
        pytest.param(
            "anonymized_at = now(), status = 'in_progress', " + _SCRUB,
            "ck_orders_anonymised_closed",
            id="an_open_order",
        ),
        pytest.param(
            "anonymized_at = now(), "
            + _SCRUB.replace("customer_note = NULL", "customer_note = 'hi'"),
            "ck_orders_anonymised_shape",
            id="keeps_the_note",
        ),
    ],
)
async def test_the_database_refuses_a_half_anonymised_order(
    db_engine: AsyncEngine, db_session: AsyncSession, assignments: str, constraint: str
) -> None:
    order = await seed_physical_order(
        db_session, line_states=("delivered",), order_status="completed"
    )
    with pytest.raises(IntegrityError, match=constraint):
        await _try(db_engine, assignments, order.order_id)


async def test_a_fully_anonymised_delivery_order_is_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, line_states=("delivered",), order_status="completed"
    )
    await _try(db_engine, f"anonymized_at = now(), {_SCRUB}", order.order_id)  # hash kept
