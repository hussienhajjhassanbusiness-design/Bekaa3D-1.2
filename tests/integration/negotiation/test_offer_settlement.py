"""VS-041 on real PostgreSQL: payment closes the offer as `paid` (SRS 5.4 step 6), buying
the STL any other way auto-closes a live offer (BR-088), a payment in flight outlives the
window, retry respects it, and a window lapsed during a pause frees a new offer (ADR-037)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.expire_offers import expire_offers
from app.main import app as main_app
from app.payments.domain.outcome import Outcome
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login
from tests.integration.negotiation.offer_checkout_support import (
    line_status,
    pay,
    seed_order_with_attempt,
)
from tests.integration.negotiation.offer_support import (
    offer_state,
    seed_offer,
    set_setting,
    shop_open,  # noqa: F401
    side_effects,
    stl,
    submit,
)
from tests.integration.ordering.checkout_support import new_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]
LIVE = ["awaiting_admin", "awaiting_customer", "accepted"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _accepted_with_order(
    db: AsyncSession, *, closes_at: datetime | None = None, attempt: str = "pending"
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """(user, offer, order, payment): an accepted offer and its unpaid order."""
    user = (await create_user(db)).id
    product = await stl(db)
    over = {"checkout_expires_at": closes_at} if closes_at else {}
    offer = await seed_offer(
        db, user_id=user, product_id=product, status="accepted", responds_by=None, **over
    )
    order, payment = await seed_order_with_attempt(
        db, user_id=user, product_id=product, offer_id=offer, attempt=attempt
    )
    return user, offer, order, payment


# ------------------------------------------------------------ paid through the offer


async def test_paying_the_offer_order_marks_the_offer_paid(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _, offer, order, payment = await _accepted_with_order(db_session)
    assert await pay(db_engine, payment) is Outcome.APPLY_PAID

    state = await offer_state(db_engine, offer)
    assert (state["status"], state["agreed_amount_cents"]) == ("paid", 800)
    assert state["rounds"][-1] == "2:system:paid:800"
    assert await line_status(db_engine, order) == "awaiting_delivery"
    effects = await side_effects(db_engine, offer)
    assert effects["audits"] == ["offer.paid"]
    # SRS 16.1: the payment's own receipt tells the customer; nothing more for the offer.
    assert effects["notifications"] == [] and effects["emails"] == []


async def test_paying_twice_settles_the_offer_once(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _, offer, _, payment = await _accepted_with_order(db_session)
    assert await pay(db_engine, payment) is Outcome.APPLY_PAID
    assert await pay(db_engine, payment) is Outcome.NOOP
    state = await offer_state(db_engine, offer)
    assert state["rounds"] == ["1:customer:submitted:800", "2:system:paid:800"]
    assert (await side_effects(db_engine, offer))["audits"] == ["offer.paid"]


# ------------------------------------------------------- bought any other way


@pytest.mark.parametrize("status", LIVE)
async def test_buying_through_the_cart_auto_closes_a_live_offer(
    db_session: AsyncSession, db_engine: AsyncEngine, status: str
) -> None:
    user = (await create_user(db_session)).id
    product = await stl(db_session)
    offer = await seed_offer(
        db_session,
        user_id=user,
        product_id=product,
        status=status,
        **({"responds_by": None} if status == "accepted" else {}),
    )
    order, payment = await seed_order_with_attempt(db_session, user_id=user, product_id=product)
    assert await pay(db_engine, payment) is Outcome.APPLY_PAID

    state = await offer_state(db_engine, offer)
    assert (state["status"], state["turn"], state["remind_at"]) == ("auto_closed", None, None)
    assert state["rounds"][-1] == "2:system:auto_closed:-"
    assert await line_status(db_engine, order) == "awaiting_delivery"
    async with db_engine.connect() as conn:
        audit = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, before_data, after_data FROM audit_logs"
                    " WHERE entity_id = :o AND action = 'offer.auto_closed'"
                ),
                {"o": offer},
            )
        ).one()
    assert audit.actor_user_id is None
    assert (audit.before_data, audit.after_data["order_id"]) == ({"status": status}, str(order))


async def test_the_cart_purchase_leaves_closed_offers_and_other_products_alone(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = (await create_user(db_session)).id
    product, other = await stl(db_session), await stl(db_session)
    rejected = await seed_offer(db_session, user_id=user, product_id=product, status="rejected")
    elsewhere = await seed_offer(db_session, user_id=user, product_id=other)
    stranger = await seed_offer(
        db_session, user_id=(await create_user(db_session)).id, product_id=product
    )
    _, payment = await seed_order_with_attempt(db_session, user_id=user, product_id=product)
    await pay(db_engine, payment)
    for offer, status in (
        (rejected, "rejected"),
        (elsewhere, "awaiting_admin"),
        (stranger, "awaiting_admin"),
    ):
        assert (await offer_state(db_engine, offer))["status"] == status


async def test_an_unpaid_order_does_not_close_the_offer(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """ADR-034 d4: only a paid line closes it; a failed attempt changes nothing."""
    user = (await create_user(db_session)).id
    product = await stl(db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product)
    await seed_order_with_attempt(db_session, user_id=user, product_id=product, attempt="failed")
    assert (await offer_state(db_engine, offer))["status"] == "awaiting_admin"


async def test_after_the_auto_close_the_customer_cannot_offer_again_on_an_owned_stl(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session)
    product = await stl(db_session)
    await seed_offer(db_session, user_id=user.id, product_id=product)
    _, payment = await seed_order_with_attempt(db_session, user_id=user.id, product_id=product)
    await pay(db_engine, payment)
    login(client, user.email)
    assert_problem(submit(client, product), 409, "PRODUCT_ALREADY_OWNED")


# ------------------------------------------------------- the window and the job


async def test_the_job_leaves_an_offer_whose_payment_is_in_flight(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    closed = datetime.now(UTC) - timedelta(seconds=1)
    _, offer, order, payment = await _accepted_with_order(db_session, closes_at=closed)
    result = await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert result["checkout_expired"] == 0
    assert (await offer_state(db_engine, offer))["status"] == "accepted"

    # The payment completes after the window: the customer paid in time, so it is honoured.
    assert await pay(db_engine, payment) is Outcome.APPLY_PAID
    assert (await offer_state(db_engine, offer))["status"] == "paid"
    assert await line_status(db_engine, order) == "awaiting_delivery"


@pytest.mark.parametrize("attempt", ["failed", "expired"])
async def test_the_job_expires_the_offer_once_its_attempt_ended_unpaid(
    db_session: AsyncSession, db_engine: AsyncEngine, attempt: str
) -> None:
    closed = datetime.now(UTC) - timedelta(seconds=1)
    _, offer, _, _ = await _accepted_with_order(db_session, closes_at=closed, attempt=attempt)
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert (await offer_state(db_engine, offer))["status"] == "checkout_expired"


async def test_a_released_order_does_not_hold_the_window_open(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    closed = datetime.now(UTC) - timedelta(seconds=1)
    _, offer, order, _ = await _accepted_with_order(db_session, closes_at=closed)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE orders SET cancelled_at = now() WHERE id = :o"), {"o": order}
        )
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert (await offer_state(db_engine, offer))["status"] == "checkout_expired"


async def test_a_window_lapsed_while_paused_frees_a_new_offer_without_cooldown(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Owner decision (ADR-037): no stretch over a pause; checkout_expired is no rejection."""
    user = await create_user(db_session)
    product = await stl(db_session)
    closes = datetime.now(UTC) + timedelta(seconds=1)
    offer = await seed_offer(
        db_session,
        user_id=user.id,
        product_id=product,
        status="accepted",
        responds_by=None,
        checkout_expires_at=closes,
    )
    login(client, user.email)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        paused = client.post(
            f"/api/v1/me/offers/{offer}/checkout",
            json={"accept_terms": True, "accept_digital_final_sale": True},
            headers=csrf(client) | {"Idempotency-Key": new_key()},
        )
        await expire_offers(_ctx(db_engine), now=closes)
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert_problem(paused, 503, "ORDERS_PAUSED")
    assert (await offer_state(db_engine, offer))["status"] == "checkout_expired"
    again = submit(client, product)
    assert again.status_code == 201, again.text


async def test_offers_left_for_a_payment_in_flight_never_stall_the_rest(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """A page full of in-flight offers is passed over, so a later one still expires."""
    now = datetime.now(UTC)
    for n in range(3):
        await _accepted_with_order(db_session, closes_at=now - timedelta(hours=3, minutes=n))
    _, later, _, _ = await _accepted_with_order(
        db_session, closes_at=now - timedelta(hours=1), attempt="failed"
    )
    result = await expire_offers(_ctx(db_engine), now=now, limit=2)
    assert (await offer_state(db_engine, later))["status"] == "checkout_expired"
    assert result["checkout_expired"] >= 1


async def test_one_cart_payment_closes_the_live_offers_on_each_of_its_stls(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = (await create_user(db_session)).id
    first, second = await stl(db_session), await stl(db_session)
    offers = [
        await seed_offer(db_session, user_id=user, product_id=first),
        await seed_offer(db_session, user_id=user, product_id=second, status="awaiting_customer"),
    ]
    order, payment = await seed_order_with_attempt(db_session, user_id=user, product_id=first)
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO order_items (order_id, user_id, payment_method, product_id,"
                " product_type, product_name_snapshot, unit_price_cents, quantity,"
                " line_total_cents, fulfillment_status)"
                " VALUES (:o, :u, 'online', :p, 'stl', 'Second', 0, 1, 0, 'pending')"
            ),
            {"o": order, "u": user, "p": second},
        )
    assert await pay(db_engine, payment) is Outcome.APPLY_PAID
    assert [(await offer_state(db_engine, o))["status"] for o in offers] == ["auto_closed"] * 2


async def test_after_a_hold_release_the_offer_can_be_checked_out_again(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """A line cancelled unpaid frees the offer (`uq_order_items_offer_once`) in its window."""
    user, offer, order, _ = await _accepted_with_order(db_session, attempt="failed")
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE orders SET cancelled_at = now(), status = 'cancelled' WHERE id = :o"),
            {"o": order},
        )
        await conn.execute(
            text(
                "UPDATE order_items SET fulfillment_status = 'cancelled', cancelled_at = now()"
                " WHERE order_id = :o"
            ),
            {"o": order},
        )
    await _login(client, db_session, user)
    again = client.post(
        f"/api/v1/me/offers/{offer}/checkout",
        json={"accept_terms": True, "accept_digital_final_sale": True},
        headers=csrf(client) | {"Idempotency-Key": new_key()},
    )
    assert again.status_code == 201, again.text
    assert again.json()["order"]["id"] != str(order)


# ---------------------------------------------------------------------- retry


async def _login(client: TestClient, db: AsyncSession, user_id: uuid.UUID) -> None:
    email = await db.scalar(text("SELECT email FROM users WHERE id = :u"), {"u": user_id})
    login(client, str(email))


def _retry(client: TestClient, order: uuid.UUID) -> Any:
    return client.post(
        f"/api/v1/me/orders/{order}/payments",
        json={},
        headers=csrf(client) | {"Idempotency-Key": new_key()},
    )


async def test_retry_of_an_offer_order_inside_the_window_starts_an_attempt(
    client: TestClient, db_session: AsyncSession
) -> None:
    user, _, order, _ = await _accepted_with_order(db_session, attempt="failed")
    await _login(client, db_session, user)
    response = _retry(client, order)
    assert response.status_code == 201, response.text
    assert response.json()["payment"]["amount_cents"] == 800


@pytest.mark.parametrize("closed_by", ["deadline", "job"])
async def test_retry_of_an_offer_order_after_the_window_is_refused(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, closed_by: str
) -> None:
    closed = datetime.now(UTC) - timedelta(seconds=1)
    user, offer, order, _ = await _accepted_with_order(
        db_session, closes_at=closed, attempt="failed"
    )
    if closed_by == "job":
        await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
        assert (await offer_state(db_engine, offer))["status"] == "checkout_expired"
    await _login(client, db_session, user)
    response = _retry(client, order)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["reason"] == "offer_checkout_expired"
    async with db_engine.connect() as conn:
        attempts = await conn.scalar(
            text("SELECT count(*) FROM payments WHERE order_id = :o"), {"o": order}
        )
    assert attempts == 1


async def test_retry_past_the_window_with_an_attempt_in_flight_resumes_it(
    client: TestClient, db_session: AsyncSession
) -> None:
    """That attempt is honoured (ADR-037 d7), so retry hands back its link, not a refusal."""
    closed = datetime.now(UTC) - timedelta(seconds=1)
    user, _, order, payment = await _accepted_with_order(db_session, closes_at=closed)
    await _login(client, db_session, user)
    response = _retry(client, order)
    assert_problem(response, 409, "PAYMENT_ALREADY_ACTIVE")
    assert response.json()["payment_id"] == str(payment)
