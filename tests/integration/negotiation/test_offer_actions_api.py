"""`POST /api/v1/me/offers/{id}/counter|accept|withdraw` (VS-040, FR-13, SRS 20.6, ADR-035):
each transition, its side effects, every refusal code, and that a refusal writes nothing."""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
import time_machine
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.negotiation.offer_support import (
    MY_OFFERS,
    act,
    offer_state,
    seed_offer,
    set_setting,
    shop_open,  # noqa: F401
    side_effects,
    stl,
    submit,
)
from tests.integration.payments.support import seed_online_order

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
ACTIONS = ["counter", "accept", "withdraw"]
COUNTER = {"amount_cents": 850, "currency": "USD"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


async def _customer(client: TestClient, db: AsyncSession, **kw: Any) -> uuid.UUID:
    user = await create_user(db, **kw)
    login(client, user.email)
    return user.id


async def _offer(
    client: TestClient, db: AsyncSession, status: str = "awaiting_customer", **over: Any
) -> tuple[uuid.UUID, uuid.UUID]:
    user = await _customer(client, db)
    product = await stl(db)
    offer = await seed_offer(db, user_id=user, product_id=product, status=status, **over)
    return user, offer


def _body(action: str) -> dict[str, Any] | None:
    return COUNTER if action == "counter" else None


async def test_customer_counter_hands_the_turn_back_and_resets_the_deadline(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    _, offer = await _offer(client, db_session, remind_at=datetime.now(UTC))
    at = datetime.now(UTC).replace(microsecond=0)
    with time_machine.travel(at, tick=False):
        response = act(client, offer, "counter", COUNTER | {"message": " how about this? "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["turn"]) == ("awaiting_admin", "admin")
    assert body["current_amount"] == {"amount_cents": 850, "currency": "USD"}
    assert datetime.fromisoformat(body["responds_by"]) == at + timedelta(hours=48)
    assert body["allowed_actions"] == ["withdraw"]
    assert body["rounds"][-1] | {"created_at": None} == {
        "sequence": 2,
        "actor": "customer",
        "action": "countered",
        "amount": {"amount_cents": 850, "currency": "USD"},
        "message": "how about this?",
        "created_at": None,
    }
    state = await offer_state(db_engine, offer)
    assert state["remind_at"] is None and state["initial_amount_cents"] == 800
    effects = await side_effects(db_engine, offer)
    assert effects["audits"] == ["offer.countered"]
    assert set(effects["notifications"]) == {"offer.countered"}
    assert effects["emails"] == []


async def test_customer_accept_freezes_the_agreed_amount(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _, offer = await _offer(client, db_session)
    at = datetime.now(UTC).replace(microsecond=0)
    with time_machine.travel(at, tick=False):
        response = act(client, offer, "accept")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["turn"], body["responds_by"]) == ("accepted", None, None)
    assert body["agreed_amount"] == {"amount_cents": 800, "currency": "USD"}
    assert datetime.fromisoformat(body["checkout_expires_at"]) == at + timedelta(hours=24)
    assert body["allowed_actions"] == []
    assert body["rounds"][-1]["action"] == "accepted"
    state = await offer_state(db_engine, offer)
    assert state["accepted_at"] == at
    effects = await side_effects(db_engine, offer)
    assert (effects["audits"], effects["emails"]) == (["offer.accepted"], ["offer_accepted"])


async def test_accept_caps_the_agreed_amount_at_todays_list_price(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Owner decision (ADR-035): the price was lowered below the amount on the table."""
    user = await _customer(client, db_session)
    product = await stl(db_session)
    offer = await seed_offer(
        db_session,
        user_id=user,
        product_id=product,
        status="awaiting_customer",
        current_amount_cents=950,
    )
    await db_session.execute(
        text("UPDATE products SET price_cents = 900 WHERE id = :p"), {"p": product}
    )
    await db_session.commit()
    body = act(client, offer, "accept").json()
    assert body["agreed_amount"]["amount_cents"] == 900
    assert body["current_amount"]["amount_cents"] == 950
    assert (await offer_state(db_engine, offer))["rounds"][-1] == "2:customer:accepted:900"


@pytest.mark.parametrize("status", ["awaiting_admin", "awaiting_customer"])
@pytest.mark.parametrize("body", [None, {}, {"reason": "  changed my mind  "}])
async def test_withdraw_from_either_awaiting_state(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    status: str,
    body: dict[str, Any] | None,
) -> None:
    _, offer = await _offer(client, db_session, status=status)
    response = act(client, offer, "withdraw", body)
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["turn"]) == ("withdrawn", None)
    expected = "changed my mind" if body and body.get("reason") else None
    assert response.json()["rounds"][-1]["message"] == expected
    effects = await side_effects(db_engine, offer)
    assert effects["audits"] == ["offer.withdrawn"] and effects["emails"] == []


async def test_withdrawing_frees_the_product_for_a_new_offer(
    client: TestClient, db_session: AsyncSession
) -> None:
    user = await _customer(client, db_session)
    product = await stl(db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product)
    assert act(client, offer, "withdraw").status_code == 200
    again = submit(client, product)
    assert again.status_code == 201, again.text


@pytest.mark.parametrize("action", ["counter", "accept"])
async def test_out_of_turn_is_409_and_writes_nothing(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, action: str
) -> None:
    _, offer = await _offer(client, db_session, status="awaiting_admin")
    before = await offer_state(db_engine, offer)
    assert_problem(act(client, offer, action, _body(action)), 409, "OFFER_NOT_YOUR_TURN")
    assert await offer_state(db_engine, offer) == before
    assert await side_effects(db_engine, offer) == {
        "audits": [],
        "notifications": [],
        "emails": [],
    }


@pytest.mark.parametrize(
    "status", ["accepted", "rejected", "withdrawn", "paid", "checkout_expired", "auto_closed"]
)
@pytest.mark.parametrize("action", ACTIONS)
async def test_a_closed_or_accepted_offer_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, status: str, action: str
) -> None:
    _, offer = await _offer(client, db_session, status=status)
    before = await offer_state(db_engine, offer)
    response = act(client, offer, action, _body(action))
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["offer_status"] == status
    assert await offer_state(db_engine, offer) == before


@pytest.mark.parametrize("action", ACTIONS)
async def test_an_expired_offer_is_410(
    client: TestClient, db_session: AsyncSession, action: str
) -> None:
    _, offer = await _offer(client, db_session, status="expired")
    assert_problem(act(client, offer, action, _body(action)), 410, "OFFER_EXPIRED")


@pytest.mark.parametrize(("offset", "code"), [(-1, 200), (0, 410), (1, 410)])
@pytest.mark.parametrize("action", ACTIONS)
async def test_the_deadline_holds_to_the_second_before_the_job_runs(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    action: str,
    offset: int,
    code: int,
) -> None:
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)
    _, offer = await _offer(client, db_session, responds_by=deadline)
    with time_machine.travel(deadline + timedelta(seconds=offset), tick=False):
        response = act(client, offer, action, _body(action))
    assert response.status_code == code, response.text
    if code == 410:
        assert response.json()["code"] == "OFFER_EXPIRED"
        assert (await offer_state(db_engine, offer))["status"] == "awaiting_customer"


async def test_counter_amount_rules(client: TestClient, db_session: AsyncSession) -> None:
    """The customer's counter meets the floor and the ceiling (ADR-035)."""
    _, offer = await _offer(client, db_session)
    below = act(client, offer, "counter", COUNTER | {"amount_cents": 699})
    assert_problem(below, 422, "OFFER_BELOW_MINIMUM")
    assert below.json()["minimum"] == {"amount_cents": 700, "currency": "USD"}
    above = act(client, offer, "counter", COUNTER | {"amount_cents": 1001})
    assert_problem(above, 422, "VALIDATION_ERROR")
    for bad in (
        {"amount_cents": 0, "currency": "USD"},
        {"amount_cents": "900", "currency": "USD"},
        {"amount_cents": 900, "currency": "EUR"},
        {"amount_cents": 900, "currency": "USD", "message": "x" * 1001},
        {"amount_cents": 900, "currency": "USD", "agreed_amount_cents": 1},
    ):
        assert_problem(act(client, offer, "counter", bad), 422, "VALIDATION_ERROR")
    assert act(client, offer, "counter", COUNTER | {"amount_cents": 1000}).status_code == 200


@pytest.mark.parametrize(
    ("change", "reason"), [("listed", "not_listed"), ("price", "not_negotiable")]
)
@pytest.mark.parametrize("action", ["counter", "accept"])
async def test_counter_and_accept_recheck_the_product(
    client: TestClient, db_session: AsyncSession, action: str, change: str, reason: str
) -> None:
    user = await _customer(client, db_session)
    product = await stl(db_session)
    offer = await seed_offer(
        db_session, user_id=user, product_id=product, status="awaiting_customer"
    )
    sql = {
        "listed": "UPDATE products SET deleted_at = now() WHERE id = :p",
        "price": "UPDATE products SET price_cents = 0 WHERE id = :p",
    }[change]
    await db_session.execute(text(sql), {"p": product})
    await db_session.commit()
    response = act(client, offer, action, _body(action))
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["reason"] == reason
    assert act(client, offer, "withdraw").status_code == 200


async def test_accepting_an_stl_bought_meanwhile_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await _customer(client, db_session)
    product = await stl(db_session)
    offer = await seed_offer(
        db_session, user_id=user, product_id=product, status="awaiting_customer"
    )
    await seed_online_order(
        db_session, user_id=user, stl_id=product, line_status="awaiting_delivery"
    )
    assert_problem(act(client, offer, "accept"), 409, "PRODUCT_ALREADY_OWNED")
    assert (await offer_state(db_engine, offer))["status"] == "awaiting_customer"
    assert await side_effects(db_engine, offer) == {
        "audits": [],
        "notifications": [],
        "emails": [],
    }


async def test_the_kill_switch_never_blocks_an_answer(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """BR-040 / INV-10."""
    _, offer = await _offer(client, db_session)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        assert act(client, offer, "accept").status_code == 200
    finally:
        await set_setting(db_engine, "accepting_orders", before)


@pytest.mark.parametrize("action", ACTIONS)
async def test_another_customers_offer_is_404(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, action: str
) -> None:
    owner = await create_user(db_session)
    offer = await seed_offer(db_session, user_id=owner.id, product_id=await stl(db_session))
    await _customer(client, db_session)
    before = await offer_state(db_engine, offer)
    assert_problem(act(client, offer, action, _body(action)), 404, "NOT_FOUND")
    assert_problem(act(client, uuid.uuid4(), action, _body(action)), 404, "NOT_FOUND")
    assert await offer_state(db_engine, offer) == before


@pytest.mark.parametrize("action", ACTIONS)
async def test_guards(client: TestClient, db_session: AsyncSession, action: str) -> None:
    owner = await create_user(db_session)
    offer = await seed_offer(db_session, user_id=owner.id, product_id=await stl(db_session))
    path = f"{MY_OFFERS}/{offer}/{action}"
    assert_problem(client.post(path, json=_body(action)), 401, "AUTH_REQUIRED")
    await _customer(client, db_session)
    assert_problem(client.post(path, json=_body(action)), 403, "CSRF_INVALID")
    await _customer(client, db_session, verified=False)
    response = act(client, offer, action, _body(action))
    assert_problem(response, 403, "EMAIL_VERIFICATION_REQUIRED")


async def test_actions_are_rate_limited_per_user(
    client: TestClient, db_session: AsyncSession
) -> None:
    user, offer = await _offer(client, db_session)
    store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
    await store.set(f"ratelimit:offer_actions:{user}", 59, ex=3600)
    await store.aclose()
    assert act(client, offer, "counter", COUNTER).status_code == 200
    assert_problem(act(client, offer, "withdraw"), 429, "RATE_LIMITED")
    assert client.get(f"{MY_OFFERS}/{offer}").status_code == 200
