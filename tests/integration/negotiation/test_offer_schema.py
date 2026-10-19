"""The DB itself refuses bad offer rows (VS-039; database-design.md 11, 15.7; SRS 11.4)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import seed_offer, stl

pytestmark = pytest.mark.integration
LIVE = ["awaiting_admin", "awaiting_customer", "accepted"]
CLOSED = ["rejected", "expired", "withdrawn", "paid", "checkout_expired", "auto_closed"]


async def _pair(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    return (await create_user(db)).id, await stl(db)


async def _refused(db: AsyncSession, name: str, **row: Any) -> None:
    user, product = await _pair(db)
    with pytest.raises(IntegrityError) as caught:
        await seed_offer(db, user_id=user, product_id=product, **row)
    await db.rollback()
    assert name in str(caught.value)


@pytest.mark.parametrize("first", LIVE)
@pytest.mark.parametrize("second", LIVE)
async def test_second_live_offer_refused_by_index(
    db_session: AsyncSession, first: str, second: str
) -> None:
    user, product = await _pair(db_session)
    await seed_offer(db_session, user_id=user, product_id=product, status=first)
    with pytest.raises(IntegrityError) as caught:
        await seed_offer(db_session, user_id=user, product_id=product, status=second)
    await db_session.rollback()
    assert "uq_offers_live" in str(caught.value)


@pytest.mark.parametrize("closed", CLOSED)
async def test_closed_offers_do_not_block_a_live_one(db_session: AsyncSession, closed: str) -> None:
    user, product = await _pair(db_session)
    await seed_offer(db_session, user_id=user, product_id=product, status=closed)
    await seed_offer(db_session, user_id=user, product_id=product, status=closed)
    await seed_offer(db_session, user_id=user, product_id=product)


async def test_live_index_is_per_customer_and_product(db_session: AsyncSession) -> None:
    user, product = await _pair(db_session)
    other_user, other_product = await _pair(db_session)
    await seed_offer(db_session, user_id=user, product_id=product)
    await seed_offer(db_session, user_id=other_user, product_id=product)
    await seed_offer(db_session, user_id=user, product_id=other_product)


@pytest.mark.parametrize(
    ("row", "name"),
    [
        ({"initial_amount_cents": 0}, "ck_offers_money"),
        ({"current_amount_cents": -1}, "ck_offers_money"),
        ({"agreed_amount_cents": 0}, "ck_offers_money"),
        ({"currency": "EUR"}, "ck_offers_money"),
        ({"turn": "customer"}, "ck_offers_turn_by_status"),
        ({"turn": None}, "ck_offers_turn_by_status"),
        ({"status": "awaiting_customer", "turn": "admin"}, "ck_offers_turn_by_status"),
        ({"status": "expired", "turn": "admin"}, "ck_offers_turn_by_status"),
        ({"status": "accepted", "agreed_amount_cents": None}, "ck_offers_accepted_shape"),
        ({"status": "accepted", "checkout_expires_at": None}, "ck_offers_accepted_shape"),
        ({"status": "rejected", "cooldown_until": None}, "ck_offers_rejected_shape"),
        ({"status": "rejected", "rejected_at": None}, "ck_offers_rejected_shape"),
    ],
    ids=lambda v: str(v),
)
async def test_check_constraints(db_session: AsyncSession, row: dict[str, Any], name: str) -> None:
    await _refused(db_session, name, **row)


async def test_awaiting_offer_needs_a_deadline(db_session: AsyncSession) -> None:
    user, product = await _pair(db_session)
    with pytest.raises(IntegrityError) as caught:
        await db_session.execute(
            text(
                "INSERT INTO offers (user_id, product_id, status, turn, initial_amount_cents,"
                " current_amount_cents) VALUES (:u, :p, 'awaiting_admin', 'admin', 800, 800)"
            ),
            {"u": user, "p": product},
        )
    await db_session.rollback()
    assert "ck_offers_turn_by_status" in str(caught.value)


async def _round(db: AsyncSession, offer_id: uuid.UUID, **row: Any) -> None:
    values = {"o": offer_id, "s": 2, "amount": None, "currency": None} | row
    await db.execute(
        text(
            "INSERT INTO offer_rounds (offer_id, sequence, actor, action, amount_cents, currency)"
            " VALUES (:o, :s, 'system', 'expired', :amount, :currency)"
        ),
        values,
    )
    await db.commit()


@pytest.mark.parametrize(
    ("row", "name"),
    [
        ({"s": 1}, "uq_offer_rounds_offer_sequence"),
        ({"s": 0}, "ck_offer_rounds_sequence_positive"),
        ({"amount": 0, "currency": "USD"}, "ck_offer_rounds_money"),
        ({"amount": 100, "currency": None}, "ck_offer_rounds_money"),
        ({"amount": None, "currency": "USD"}, "ck_offer_rounds_money"),
        ({"amount": 100, "currency": "EUR"}, "ck_offer_rounds_money"),
    ],
    ids=lambda v: str(v),
)
async def test_round_constraints(db_session: AsyncSession, row: dict[str, Any], name: str) -> None:
    user, product = await _pair(db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product)
    with pytest.raises(IntegrityError) as caught:
        await _round(db_session, offer, **row)
    await db_session.rollback()
    assert name in str(caught.value)


async def test_a_round_without_an_amount_is_fine(db_session: AsyncSession) -> None:
    user, product = await _pair(db_session)
    await _round(db_session, await seed_offer(db_session, user_id=user, product_id=product))


async def test_order_item_offer_id_must_name_an_offer(db_session: AsyncSession) -> None:
    """The FK 03a4730dd046 deferred to VS-039 is in place and validated."""
    validated = await db_session.scalar(
        text("SELECT convalidated FROM pg_constraint WHERE conname = 'order_items_offer_id_fkey'")
    )
    assert validated is True


async def test_offers_and_rounds_refuse_deleting_their_parents(db_session: AsyncSession) -> None:
    user, product = await _pair(db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product)
    with pytest.raises(IntegrityError):
        await db_session.execute(text("DELETE FROM offers WHERE id = :o"), {"o": offer})
    await db_session.rollback()
    with pytest.raises(IntegrityError):
        await db_session.execute(text("DELETE FROM products WHERE id = :p"), {"p": product})
    await db_session.rollback()


async def test_timestamps_are_timestamptz(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns"
            " WHERE table_name IN ('offers', 'offer_rounds') AND data_type LIKE 'timestamp%'"
        )
    )
    types = {(t, c): d for t, c, d in rows.all()}
    assert types and set(types.values()) == {"timestamp with time zone"}
