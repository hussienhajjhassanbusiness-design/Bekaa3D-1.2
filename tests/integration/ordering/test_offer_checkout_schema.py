"""`uq_order_items_offer_once` (VS-041, ADR-037): the database itself refuses a second line
for one offer unless every earlier one was cancelled unpaid - "at most once" survives a
refund, which frees the ownership index but never this one."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_checkout_support import seed_order_with_attempt
from tests.integration.negotiation.offer_support import seed_offer, stl

pytestmark = pytest.mark.integration


async def _offer_with_line(db: AsyncSession, line: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = (await create_user(db)).id
    product = await stl(db)
    offer = await seed_offer(db, user_id=user, product_id=product, status="accepted")
    order, _ = await seed_order_with_attempt(
        db, user_id=user, product_id=product, offer_id=offer, attempt="failed"
    )
    cancelled = "now()" if line == "cancelled" else "NULL"
    await db.execute(
        text(
            "UPDATE order_items SET fulfillment_status = :s,"
            f" cancelled_at = {cancelled} WHERE order_id = :o"
        ),
        {"s": line, "o": order},
    )
    await db.commit()
    return user, product, offer


async def _second_line(
    db: AsyncSession, user: uuid.UUID, product: uuid.UUID, offer: uuid.UUID
) -> None:
    await seed_order_with_attempt(db, user_id=user, product_id=product, offer_id=offer)


@pytest.mark.parametrize("line", ["pending", "awaiting_delivery", "refunded"])
async def test_a_second_line_for_one_offer_is_refused(db_session: AsyncSession, line: str) -> None:
    user, product, offer = await _offer_with_line(db_session, line)
    with pytest.raises(IntegrityError) as caught:
        await _second_line(db_session, user, product, offer)
    await db_session.rollback()
    message = str(caught.value.orig)
    # A refunded line has left the ownership index, so only the new index can refuse it.
    expected = "uq_order_items_offer_once" if line == "refunded" else "uq_order_items_"
    assert expected in message


async def test_a_cancelled_unpaid_line_frees_the_offer(db_session: AsyncSession) -> None:
    user, product, offer = await _offer_with_line(db_session, "cancelled")
    await _second_line(db_session, user, product, offer)
    count = await db_session.scalar(
        text("SELECT count(*) FROM order_items WHERE offer_id = :f"), {"f": offer}
    )
    assert count == 2
