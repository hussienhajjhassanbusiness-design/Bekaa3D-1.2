"""`POST /api/v1/admin/offers/{id}/counter|accept|reject` (VS-040, FR-13, SRS 20.6, ADR-035):
the admin boundary on each route, each transition and its emails, the cooldown it arms, and
a whole negotiation kept round by round."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import time_machine
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    login,
    mfa_admin,
)
from tests.integration.negotiation.offer_support import (
    ADMIN_OFFERS,
    act,
    offer_state,
    seed_offer,
    set_setting,
    shop_open,  # noqa: F401
    side_effects,
    stl,
    submit,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]
ACTIONS = ["counter", "accept", "reject"]
COUNTER = {"amount_cents": 950, "currency": "USD"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


def as_customer(email: str, call: Callable[[TestClient], httpx.Response]) -> httpx.Response:
    """One request in its own client. A client's lifespan rebinds the app's engine to its
    loop, so a test that needs two actors never keeps two clients open at once."""
    with client_for(main_app) as shopper:
        login(shopper, email)
        return call(shopper)


async def as_admin(
    db: AsyncSession, call: Callable[[TestClient], httpx.Response]
) -> httpx.Response:
    with client_for(main_app) as admin:
        await mfa_admin(admin, db)
        return call(admin)


def _amount(cents: int) -> dict[str, Any]:
    return COUNTER | {"amount_cents": cents}


def _body(action: str) -> dict[str, Any] | None:
    return COUNTER if action == "counter" else None


async def _offer(db: AsyncSession, status: str = "awaiting_admin", **over: Any) -> uuid.UUID:
    user = await create_user(db)
    return await seed_offer(db, user_id=user.id, product_id=await stl(db), status=status, **over)


@pytest.mark.parametrize("action", ACTIONS)
async def test_the_admin_boundary_on_every_action(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, action: str
) -> None:
    owner = await create_user(db_session)
    offer = await seed_offer(db_session, user_id=owner.id, product_id=await stl(db_session))
    path = f"{ADMIN_OFFERS}/{offer}/{action}"
    before = await offer_state(db_engine, offer)
    assert_problem(client.post(path, json=_body(action)), 401, "AUTH_REQUIRED")
    login(client, owner.email)
    assert_problem(act(client, offer, action, _body(action), admin=True), 404, "NOT_FOUND")
    admin = await create_user(db_session, role=UserRole.ADMIN)
    login(client, admin.email)
    assert act(client, offer, action, _body(action), admin=True).status_code == 401
    await mfa_admin(client, db_session)
    assert_problem(client.post(path, json=_body(action)), 403, "CSRF_INVALID")
    assert await offer_state(db_engine, offer) == before


async def test_admin_counter_passes_the_turn_and_emails_the_customer(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    offer = await _offer(db_session)
    await mfa_admin(client, db_session)
    at = datetime.now(UTC).replace(microsecond=0)
    with time_machine.travel(at, tick=False):
        response = act(client, offer, "counter", COUNTER | {"message": "best I can do"}, admin=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["turn"]) == ("awaiting_customer", "customer")
    assert datetime.fromisoformat(body["responds_by"]) == at + timedelta(hours=48)
    assert body["allowed_actions"] == [] and body["customer"]["id"]
    state = await offer_state(db_engine, offer)
    assert state["remind_at"] == at + timedelta(hours=36)
    assert state["rounds"] == ["1:customer:submitted:800", "2:admin:countered:950"]
    effects = await side_effects(db_engine, offer)
    assert effects == {
        "audits": ["offer.countered"],
        "notifications": ["offer.countered"],
        "emails": ["offer_countered"],
    }


async def test_admin_counter_has_a_ceiling_but_no_floor(
    client: TestClient, db_session: AsyncSession
) -> None:
    offer = await _offer(db_session)
    await mfa_admin(client, db_session)
    above = act(client, offer, "counter", COUNTER | {"amount_cents": 1001}, admin=True)
    assert_problem(above, 422, "VALIDATION_ERROR")
    assert (
        act(client, offer, "counter", COUNTER | {"amount_cents": 1}, admin=True).status_code == 200
    )


@pytest.mark.parametrize(("list_price", "agreed"), [(1000, 800), (800, 800), (750, 750)])
async def test_admin_accept_caps_at_todays_list_price(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    list_price: int,
    agreed: int,
) -> None:
    user = await create_user(db_session)
    product = await stl(db_session)
    offer = await seed_offer(db_session, user_id=user.id, product_id=product)
    await db_session.execute(
        text("UPDATE products SET price_cents = :c WHERE id = :p"), {"c": list_price, "p": product}
    )
    await db_session.commit()
    await mfa_admin(client, db_session)
    at = datetime.now(UTC).replace(microsecond=0)
    with time_machine.travel(at, tick=False):
        body = act(client, offer, "accept", admin=True).json()
    assert (body["status"], body["agreed_amount"]["amount_cents"]) == ("accepted", agreed)
    assert datetime.fromisoformat(body["checkout_expires_at"]) == at + timedelta(hours=24)
    effects = await side_effects(db_engine, offer)
    assert effects["emails"] == ["offer_accepted"]
    assert effects["notifications"] == ["offer.accepted"]


async def test_reject_arms_the_cooldown_and_a_resubmission_waits_for_it(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    customer = await create_user(db_session)
    product = await stl(db_session)
    offer = await seed_offer(db_session, user_id=customer.id, product_id=product)
    frozen: list[datetime] = []

    def reject_at(admin: TestClient) -> httpx.Response:
        """Frozen after the login, so the session is never issued in the future."""
        frozen.append(datetime.now(UTC).replace(microsecond=0))
        with time_machine.travel(frozen[0], tick=False):
            return act(admin, offer, "reject", {"reason": "  too low  "}, admin=True)

    response = await as_admin(db_session, reject_at)
    at = frozen[0]
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["turn"]) == ("rejected", None)
    assert datetime.fromisoformat(body["cooldown_until"]) == at + timedelta(days=7)
    assert body["rounds"][-1]["message"] == "too low"
    assert (await side_effects(db_engine, offer))["emails"] == ["offer_rejected"]
    retry = as_customer(customer.email, lambda c: submit(c, product))
    assert_problem(retry, 422, "OFFER_COOLDOWN_ACTIVE")


async def test_with_a_zero_cooldown_the_customer_may_offer_again_at_once(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    customer = await create_user(db_session)
    product = await stl(db_session)
    offer = await seed_offer(db_session, user_id=customer.id, product_id=product)
    before = await set_setting(db_engine, "offer_rejection_cooldown", "0")
    try:
        rejected = await as_admin(db_session, lambda c: act(c, offer, "reject", admin=True))
        assert rejected.status_code == 200, rejected.text
        retry = as_customer(customer.email, lambda c: submit(c, product))
        assert retry.status_code == 201, retry.text
    finally:
        await set_setting(db_engine, "offer_rejection_cooldown", before)


@pytest.mark.parametrize("action", ACTIONS)
async def test_out_of_turn_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, action: str
) -> None:
    offer = await _offer(db_session, status="awaiting_customer")
    await mfa_admin(client, db_session)
    before = await offer_state(db_engine, offer)
    response = act(client, offer, action, _body(action), admin=True)
    assert_problem(response, 409, "OFFER_NOT_YOUR_TURN")
    assert await offer_state(db_engine, offer) == before
    assert await side_effects(db_engine, offer) == {
        "audits": [],
        "notifications": [],
        "emails": [],
    }


@pytest.mark.parametrize("status", ["accepted", "rejected", "withdrawn", "paid", "auto_closed"])
@pytest.mark.parametrize("action", ACTIONS)
async def test_a_closed_or_accepted_offer_is_409(
    client: TestClient, db_session: AsyncSession, status: str, action: str
) -> None:
    offer = await _offer(db_session, status=status)
    await mfa_admin(client, db_session)
    response = act(client, offer, action, _body(action), admin=True)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    assert response.json()["offer_status"] == status


@pytest.mark.parametrize(("offset", "code"), [(-1, 200), (0, 410), (1, 410)])
@pytest.mark.parametrize("action", ACTIONS)
async def test_the_deadline_holds_to_the_second(
    client: TestClient, db_session: AsyncSession, action: str, offset: int, code: int
) -> None:
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)
    offer = await _offer(db_session, responds_by=deadline)
    await mfa_admin(client, db_session)
    with time_machine.travel(deadline + timedelta(seconds=offset), tick=False):
        response = act(client, offer, action, _body(action), admin=True)
    assert response.status_code == code, response.text


async def test_unknown_offer_is_404(client: TestClient, db_session: AsyncSession) -> None:
    await mfa_admin(client, db_session)
    for action in ACTIONS:
        response = act(client, uuid.uuid4(), action, _body(action), admin=True)
        assert_problem(response, 404, "NOT_FOUND")


async def test_a_whole_negotiation_is_kept_round_by_round(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """BR-082, BR-091: unlimited alternating counters, then acceptance; every round kept."""
    customer = await create_user(db_session)
    product = await stl(db_session)
    email = customer.email
    offer = uuid.UUID(as_customer(email, lambda c: submit(c, product, 700)).json()["id"])
    steps = [
        await as_admin(db_session, lambda c: act(c, offer, "counter", _amount(950), admin=True)),
        as_customer(email, lambda c: act(c, offer, "counter", _amount(800))),
        await as_admin(db_session, lambda c: act(c, offer, "counter", _amount(900), admin=True)),
        as_customer(email, lambda c: c.get(f"/api/v1/me/offers/{offer}")),
        as_customer(email, lambda c: act(c, offer, "accept")),
        await as_admin(db_session, lambda c: c.get(f"{ADMIN_OFFERS}/{offer}")),
    ]
    assert all(step.status_code == 200 for step in steps), [s.text for s in steps]
    mine, accepted, detail = steps[3].json(), steps[4].json(), steps[5].json()
    assert mine["allowed_actions"] == ["counter", "accept", "withdraw"]
    assert accepted["agreed_amount"]["amount_cents"] == 900
    assert [(r["sequence"], r["actor"], r["action"]) for r in detail["rounds"]] == [
        (1, "customer", "submitted"),
        (2, "admin", "countered"),
        (3, "customer", "countered"),
        (4, "admin", "countered"),
        (5, "customer", "accepted"),
    ]
    assert detail["initial_amount"]["amount_cents"] == 700
    effects = await side_effects(db_engine, offer)
    assert effects["emails"] == ["offer_countered", "offer_countered", "offer_accepted"]
