"""The DB itself refuses bad offer rows (VS-039; database-design.md 11, 15.7; SRS 11.4)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import physical, seed_offer, stl
from tests.integration.payments.support import seed_online_order

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
        ({"status": "paid", "agreed_amount_cents": None}, "ck_offers_accepted_shape"),
        ({"status": "checkout_expired", "accepted_at": None}, "ck_offers_accepted_shape"),
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


async def _offer_on_line(
    db: AsyncSession, offer_user: str, offer_product: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """An STL order line, and an accepted offer by the same or another user and product."""
    user, product = await _pair(db)
    other_user, other_product = await _pair(db)
    order = await seed_online_order(db, user_id=user, stl_id=product)
    offer = await seed_offer(
        db,
        user_id=user if offer_user == "same" else other_user,
        product_id=product if offer_product == "same" else other_product,
        status="accepted",
    )
    return order, offer


@pytest.mark.parametrize(
    ("offer_user", "offer_product"),
    [("other", "same"), ("same", "other"), ("other", "other")],
)
async def test_a_line_cannot_carry_another_customers_or_products_offer(
    db_session: AsyncSession, offer_user: str, offer_product: str
) -> None:
    """ADR-034: VS-041 cannot price a line from an offer that is not that line's own."""
    order, offer = await _offer_on_line(db_session, offer_user, offer_product)
    with pytest.raises(IntegrityError) as caught:
        await _set_line_offer(db_session, order, offer)
    await db_session.rollback()
    assert "fk_order_items_offer_owner" in str(caught.value)


async def test_a_line_may_carry_its_own_offer(db_session: AsyncSession) -> None:
    order, offer = await _offer_on_line(db_session, "same", "same")
    await _set_line_offer(db_session, order, offer)


async def _set_line_offer(db: AsyncSession, order: uuid.UUID, offer: uuid.UUID) -> None:
    await db.execute(
        text("UPDATE order_items SET offer_id = :f WHERE order_id = :o"), {"f": offer, "o": order}
    )
    await db.commit()


async def test_a_physical_line_cannot_carry_an_offer(db_session: AsyncSession) -> None:
    """The offer service refuses physical products; the DB refuses the line regardless."""
    user = (await create_user(db_session)).id
    product = await physical(db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product, status="accepted")
    order = uuid.uuid4()
    now = datetime.now(UTC)
    rows = {
        "orders": {
            "id": order,
            "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
            "user_id": user,
            "customer_email_snapshot": "buyer@example.com",
            "source": "offer",
            "status": "in_progress",
            "subtotal_cents": 800,
            "total_cents": 800,
            "terms_accepted_at": now,
            "placed_at": now,
            "payment_method": "cash",
            "fulfillment_method": "pickup",
            "cash_terms_accepted_at": now,
            "contact_phone_snapshot": "+96170123456",
            "contact_phone_hash": "hash",
        },
        "order_items": {
            "order_id": order,
            "user_id": user,
            "product_id": product,
            "offer_id": offer,
            "product_type": "physical",
            "product_name_snapshot": "Lamp",
            "unit_price_cents": 800,
            "quantity": 1,
            "line_total_cents": 800,
            "fulfillment_status": "pending",
            "payment_method": "cash",
            "lead_time_days_snapshot": 3,
            "batch_size_snapshot": 2,
        },
    }
    with pytest.raises(IntegrityError) as caught:
        for table, row in rows.items():
            columns, values = ", ".join(row), ", ".join(f":{c}" for c in row)
            await db_session.execute(
                text(f"INSERT INTO {table} ({columns}) VALUES ({values})"), row
            )
        await db_session.commit()
    await db_session.rollback()
    assert "ck_order_items_offer_is_stl" in str(caught.value)


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


@pytest.mark.parametrize("status", [s for s in LIVE + CLOSED if s != "awaiting_customer"])
async def test_only_the_customers_turn_carries_a_reminder(
    db_session: AsyncSession, status: str
) -> None:
    """VS-040: SRS 16.1 reminds only the customer; ADR-035."""
    await _refused(
        db_session,
        "ck_offers_remind_at_awaiting_customer",
        status=status,
        remind_at=datetime.now(UTC),
    )


async def test_the_customers_turn_may_carry_a_reminder(db_session: AsyncSession) -> None:
    user, product = await _pair(db_session)
    await seed_offer(
        db_session,
        user_id=user,
        product_id=product,
        status="awaiting_customer",
        remind_at=datetime.now(UTC),
    )
