"""`POST /api/v1/offers`, `GET /api/v1/me/offers[/{id}]` (VS-039, FR-13, ADR-034)."""

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
    OFFERS,
    offer_rows,
    physical,
    seed_offer,
    set_setting,
    shop_open,  # noqa: F401
    stl,
    submit,
)
from tests.integration.payments.support import seed_online_order

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


async def _customer(client: TestClient, db: AsyncSession, **kw: Any) -> uuid.UUID:
    user = await create_user(db, **kw)
    login(client, user.email)
    return user.id


async def test_submit_opens_an_offer_on_the_admins_turn(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    product = await stl(db_session)
    user = await _customer(client, db_session)
    at = datetime.now(UTC).replace(microsecond=0)
    with time_machine.travel(at, tick=False):
        response = submit(client, product, 800, message="  Would you take 8?  ")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["turn"]) == ("awaiting_admin", "admin")
    assert (
        body["current_amount"] == body["initial_amount"] == {"amount_cents": 800, "currency": "USD"}
    )
    assert datetime.fromisoformat(body["responds_by"]) == at + timedelta(seconds=172_800)
    assert body["agreed_amount"] is None and body["allowed_actions"] == []
    assert body["product"]["id"] == str(product) and body["product"]["name"] == "Lamp"
    [first] = body["rounds"]
    assert first | {"created_at": None} == {
        "sequence": 1,
        "actor": "customer",
        "action": "submitted",
        "amount": {"amount_cents": 800, "currency": "USD"},
        "message": "Would you take 8?",
        "created_at": None,
    }
    rows = await offer_rows(db_engine, user)
    assert (rows.offers, rows.rounds, rows.audits) == (1, 1, 1)
    assert rows.notifications >= 1
    audit = (
        await db_session.execute(
            text(
                "SELECT entity_type, after_data FROM audit_logs WHERE entity_id = :o"
                " AND action = 'offer.submitted'"
            ),
            {"o": body["id"]},
        )
    ).one()
    assert audit.entity_type == "Offer" and audit.after_data["amount_cents"] == 800
    payload = await db_session.scalar(
        text("SELECT payload FROM notifications WHERE user_id = :a AND type = 'offer'"),
        {"a": admin.id},
    )
    assert payload == {
        "event": "offer.submitted",
        "offer_id": body["id"],
        "product_id": str(product),
        "product_name": "Lamp",
        "amount_cents": 800,
        "currency": "USD",
    }


async def test_a_blank_message_is_stored_as_none(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await stl(db_session)
    await _customer(client, db_session)
    response = submit(client, product, message="   ")
    assert response.status_code == 201, response.text
    assert response.json()["rounds"][0]["message"] is None


async def test_kill_switch_refuses_submission_and_writes_nothing(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        paused = submit(client, product)
        reads = client.get(MY_OFFERS)
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert_problem(paused, 503, "ORDERS_PAUSED")
    assert reads.status_code == 200
    assert (await offer_rows(db_engine, user)).offers == 0
    assert submit(client, product).status_code == 201


async def test_kill_switch_does_not_touch_existing_offers(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """ADR-034: paused shop still shows and keeps live offers (expiry: test_expire_offers)."""
    product = await stl(db_session)
    user = await _customer(client, db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        detail = client.get(f"{MY_OFFERS}/{offer}")
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert detail.status_code == 200 and detail.json()["status"] == "awaiting_admin"


async def test_physical_product_is_not_negotiable(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    product = await physical(db_session)
    user = await _customer(client, db_session)
    response = submit(client, product)
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["reason"] == "not_negotiable"
    assert (await offer_rows(db_engine, user)).offers == 0


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("UPDATE products SET is_visible = false WHERE id = :p", "not_listed"),
        ("UPDATE products SET deleted_at = now() WHERE id = :p", "not_listed"),
        ("UPDATE products SET is_available = false WHERE id = :p", "unavailable"),
    ],
)
async def test_unlisted_or_unavailable_stl_is_refused(
    client: TestClient, db_session: AsyncSession, change: str, reason: str
) -> None:
    product = await stl(db_session)
    await db_session.execute(text(change), {"p": product})
    await db_session.commit()
    await _customer(client, db_session)
    response = submit(client, product)
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["reason"] == reason


async def test_unknown_product_is_refused(client: TestClient, db_session: AsyncSession) -> None:
    await _customer(client, db_session)
    response = submit(client, uuid.uuid4())
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["reason"] == "not_listed"


@pytest.mark.parametrize("line_status", ["awaiting_delivery", "delivered"])
async def test_owned_stl_is_refused(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, line_status: str
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    await seed_online_order(db_session, user_id=user, stl_id=product, line_status=line_status)
    assert_problem(submit(client, product), 409, "PRODUCT_ALREADY_OWNED")
    assert (await offer_rows(db_engine, user)).offers == 0


@pytest.mark.parametrize("line_status", ["pending", "refunded"])
async def test_unpaid_or_refunded_stl_may_be_offered_on(
    client: TestClient, db_session: AsyncSession, line_status: str
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    await seed_online_order(db_session, user_id=user, stl_id=product, line_status=line_status)
    assert submit(client, product).status_code == 201


async def test_floor_is_exact(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Price 999 at 70 %: the floor is 700 (699.3 rounded up), never 699."""
    product = await stl(db_session, price_cents=999)
    user = await _customer(client, db_session)
    below = submit(client, product, 699)
    assert_problem(below, 422, "OFFER_BELOW_MINIMUM")
    assert below.json()["minimum"] == {"amount_cents": 700, "currency": "USD"}
    assert (await offer_rows(db_engine, user)).offers == 0
    assert submit(client, product, 700).status_code == 201


async def test_floor_follows_the_setting(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    product = await stl(db_session)
    await _customer(client, db_session)
    before = await set_setting(db_engine, "minimum_offer_percentage", "0")
    try:
        response = submit(client, product, 1)
    finally:
        await set_setting(db_engine, "minimum_offer_percentage", before)
    assert response.status_code == 201, response.text


async def test_above_list_price_is_a_validation_error(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await stl(db_session)
    await _customer(client, db_session)
    response = submit(client, product, 1001)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert submit(client, product, 1000).status_code == 201


@pytest.mark.parametrize("status", ["awaiting_admin", "awaiting_customer", "accepted"])
async def test_second_live_offer_is_409(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, status: str
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    await seed_offer(db_session, user_id=user, product_id=product, status=status)
    assert_problem(submit(client, product), 409, "OFFER_ALREADY_ACTIVE")
    rows = await offer_rows(db_engine, user)
    assert (rows.offers, rows.rounds, rows.audits) == (1, 1, 0)


@pytest.mark.parametrize("status", ["expired", "withdrawn", "paid", "checkout_expired"])
async def test_a_closed_offer_does_not_block_a_new_one(
    client: TestClient, db_session: AsyncSession, status: str
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    await seed_offer(db_session, user_id=user, product_id=product, status=status)
    assert submit(client, product).status_code == 201


@pytest.mark.parametrize(
    ("offset", "allowed"),
    [(-timedelta(seconds=1), False), (timedelta(0), True), (timedelta(seconds=1), True)],
    ids=["expiry-1s", "at-expiry", "expiry+1s"],
)
async def test_cooldown_boundaries(
    client: TestClient,
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    offset: timedelta,
    allowed: bool,
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    until = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    await seed_offer(
        db_session, user_id=user, product_id=product, status="rejected", cooldown_until=until
    )
    with time_machine.travel(until + offset, tick=False):
        login(client, (await _email(db_session, user)))
        response = submit(client, product)
    if allowed:
        assert response.status_code == 201, response.text
    else:
        assert_problem(response, 422, "OFFER_COOLDOWN_ACTIVE")
        assert datetime.fromisoformat(response.json()["cooldown_until"]) == until
        rows = await offer_rows(db_engine, user)
        assert (rows.offers, rows.audits, rows.notifications) == (1, 0, 0)


async def test_the_latest_rejection_rules_the_cooldown(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    now = datetime.now(UTC)
    for until in (now - timedelta(days=1), now + timedelta(days=2)):
        await seed_offer(
            db_session, user_id=user, product_id=product, status="rejected", cooldown_until=until
        )
    assert_problem(submit(client, product), 422, "OFFER_COOLDOWN_ACTIVE")


async def test_cooldown_is_per_product(client: TestClient, db_session: AsyncSession) -> None:
    rejected, other = await stl(db_session), await stl(db_session)
    user = await _customer(client, db_session)
    await seed_offer(db_session, user_id=user, product_id=rejected, status="rejected")
    assert submit(client, other).status_code == 201


async def _email(db: AsyncSession, user_id: uuid.UUID) -> str:
    return str(await db.scalar(text("SELECT email FROM users WHERE id = :u"), {"u": user_id}))


@pytest.mark.parametrize(
    "body",
    [
        {"amount_cents": 0},
        {"amount_cents": -5},
        {"amount_cents": 800.0},
        {"amount_cents": "800"},
        {"amount_cents": 2**63},
        {"currency": "EUR"},
        {"currency": None},
        {"message": "x" * 1001},
        {"message": "nul\x00byte"},
        {"surprise": True},
    ],
    ids=lambda b: str(sorted(b)),
)
async def test_malformed_bodies_are_422(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine, body: dict[str, Any]
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    assert_problem(submit(client, product, **body), 422, "VALIDATION_ERROR")
    assert (await offer_rows(db_engine, user)).offers == 0


async def test_a_multiline_message_is_kept(client: TestClient, db_session: AsyncSession) -> None:
    product = await stl(db_session)
    await _customer(client, db_session)
    response = submit(client, product, message="line one\nline two")
    assert response.json()["rounds"][0]["message"] == "line one\nline two"


async def test_anonymous_is_401(client: TestClient, db_session: AsyncSession) -> None:
    product = await stl(db_session)
    body = {"product_id": str(product), "amount_cents": 800, "currency": "USD"}
    assert_problem(client.post(OFFERS, json=body), 401, "AUTH_REQUIRED")
    assert_problem(client.get(MY_OFFERS), 401, "AUTH_REQUIRED")


async def test_unverified_cannot_submit_but_can_read(
    client: TestClient, db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session, verified=False)
    assert_problem(submit(client, product), 403, "EMAIL_VERIFICATION_REQUIRED")
    assert client.get(MY_OFFERS).status_code == 200
    assert (await offer_rows(db_engine, user)).offers == 0


async def test_missing_csrf_is_403(client: TestClient, db_session: AsyncSession) -> None:
    product = await stl(db_session)
    await _customer(client, db_session)
    body = {"product_id": str(product), "amount_cents": 800, "currency": "USD"}
    assert_problem(client.post(OFFERS, json=body), 403, "CSRF_INVALID")


async def test_submission_is_rate_limited_per_user(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
    await store.set(f"ratelimit:offers:{user}", 20, ex=3600)
    await store.aclose()
    assert_problem(submit(client, product), 429, "RATE_LIMITED")
    assert client.get(MY_OFFERS).status_code == 200
    with client_for(main_app) as other:
        await _customer(other, db_session)
        assert submit(other, product).status_code == 201


async def test_list_is_own_newest_first_filtered_and_paged(
    client: TestClient, db_session: AsyncSession
) -> None:
    user = await _customer(client, db_session)
    stranger = (await create_user(db_session)).id
    base = datetime.now(UTC) - timedelta(hours=1)
    products = [await stl(db_session) for _ in range(3)]
    ids = [
        await seed_offer(
            db_session,
            user_id=user,
            product_id=p,
            status=s,
            created_at=base + timedelta(minutes=i),
        )
        for i, (p, s) in enumerate(
            zip(products, ["expired", "awaiting_admin", "rejected"], strict=True)
        )
    ]
    await seed_offer(db_session, user_id=stranger, product_id=products[0])
    first = client.get(MY_OFFERS, params={"limit": 2}).json()
    second = client.get(MY_OFFERS, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [o["id"] for o in first["items"] + second["items"]] == [str(i) for i in ids[::-1]]
    assert second["next_cursor"] is None
    by_status = client.get(MY_OFFERS, params={"status": "awaiting_admin"}).json()["items"]
    assert [o["id"] for o in by_status] == [str(ids[1])]
    by_product = client.get(MY_OFFERS, params={"product_id": str(products[0])}).json()["items"]
    assert [o["id"] for o in by_product] == [str(ids[0])]
    assert "rounds" not in first["items"][0]


@pytest.mark.parametrize("cursor", ["garbage", "Zm9v", "MjAyNi0xMC0yMHxub3QtYS11dWlk"])
async def test_a_bad_cursor_is_422(
    client: TestClient, db_session: AsyncSession, cursor: str
) -> None:
    await _customer(client, db_session)
    assert_problem(client.get(MY_OFFERS, params={"cursor": cursor}), 422, "VALIDATION_ERROR")


async def test_detail_has_the_full_history(client: TestClient, db_session: AsyncSession) -> None:
    product = await stl(db_session)
    user = await _customer(client, db_session)
    offer = await seed_offer(db_session, user_id=user, product_id=product, status="expired")
    await db_session.execute(
        text(
            "INSERT INTO offer_rounds (offer_id, sequence, actor, action)"
            " VALUES (:o, 2, 'system', 'expired')"
        ),
        {"o": offer},
    )
    await db_session.commit()
    body = client.get(f"{MY_OFFERS}/{offer}").json()
    assert [(r["sequence"], r["actor"], r["action"]) for r in body["rounds"]] == [
        (1, "customer", "submitted"),
        (2, "system", "expired"),
    ]
    assert body["rounds"][1]["amount"] is None and body["turn"] is None


async def test_another_customers_offer_is_404(client: TestClient, db_session: AsyncSession) -> None:
    product = await stl(db_session)
    stranger = (await create_user(db_session)).id
    theirs = await seed_offer(db_session, user_id=stranger, product_id=product)
    await _customer(client, db_session)
    mine = client.get(f"{MY_OFFERS}/{theirs}")
    unknown = client.get(f"{MY_OFFERS}/{uuid.uuid4()}")
    assert_problem(mine, 404, "NOT_FOUND")
    ignore = {"request_id": None, "instance": None}
    assert mine.json() | ignore == unknown.json() | ignore
    listed = client.get(MY_OFFERS, params={"product_id": str(product)}).json()["items"]
    assert listed == []
