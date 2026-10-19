"""`GET /api/v1/admin/offers[/{id}]` (VS-039, api-endpoints.md 21, ADR-034): the queue's
order, filters and cursor, the customer it names, and the admin boundary on both routes."""

import base64
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
from tests.integration.negotiation.offer_support import ADMIN_OFFERS, seed_offer, stl

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
_RANK_OUT_OF_RANGE = base64.urlsafe_b64encode(
    f"9|2026-10-20T00:00+00:00|{uuid.UUID(int=0)}".encode()
).decode()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


def _routes(offer_id: uuid.UUID) -> list[str]:
    return [ADMIN_OFFERS, f"{ADMIN_OFFERS}/{offer_id}"]


async def _offer(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user = await create_user(db)
    return user.id, await seed_offer(db, user_id=user.id, product_id=await stl(db))


async def test_anonymous_is_401_on_every_route(
    client: TestClient, db_session: AsyncSession
) -> None:
    _, offer = await _offer(db_session)
    for path in _routes(offer):
        assert_problem(client.get(path), 401, "AUTH_REQUIRED")


async def test_a_customer_gets_404_on_every_route_even_for_their_own_offer(
    client: TestClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    offer = await seed_offer(db_session, user_id=user.id, product_id=await stl(db_session))
    login(client, user.email)
    for path in _routes(offer):
        assert_problem(client.get(path), 404, "NOT_FOUND")


async def test_an_admin_without_mfa_is_refused(
    client: TestClient, db_session: AsyncSession
) -> None:
    _, offer = await _offer(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    login(client, admin.email)
    for path in _routes(offer):
        assert client.get(path).status_code == 401


async def test_detail_names_the_customer_and_has_every_round(
    client: TestClient, db_session: AsyncSession
) -> None:
    customer = await create_user(db_session)
    offer = await seed_offer(
        db_session, user_id=customer.id, product_id=await stl(db_session), status="expired"
    )
    await db_session.execute(
        text(
            "INSERT INTO offer_rounds (offer_id, sequence, actor, action)"
            " VALUES (:o, 2, 'system', 'expired')"
        ),
        {"o": offer},
    )
    await db_session.commit()
    await mfa_admin(client, db_session)
    body = client.get(f"{ADMIN_OFFERS}/{offer}").json()
    assert body["customer"] == {"id": str(customer.id), "email": customer.email}
    assert [r["action"] for r in body["rounds"]] == ["submitted", "expired"]
    assert body["allowed_actions"] == []
    assert_problem(client.get(f"{ADMIN_OFFERS}/{uuid.uuid4()}"), 404, "NOT_FOUND")


async def test_queue_order_admins_turn_first_then_customers_then_accepted_then_closed(
    client: TestClient, db_session: AsyncSession
) -> None:
    customer = (await create_user(db_session)).id
    now = datetime.now(UTC)
    seeded: dict[str, uuid.UUID] = {}
    for name, status, responds_by, created_hours in [
        ("closed_old", "expired", now - timedelta(days=9), 90),
        ("closed_new", "withdrawn", now - timedelta(days=1), 10),
        ("accepted", "accepted", None, 50),
        ("customer_soon", "awaiting_customer", now + timedelta(hours=1), 40),
        ("customer_late", "awaiting_customer", now + timedelta(hours=9), 41),
        ("admin_late", "awaiting_admin", now + timedelta(hours=8), 30),
        ("admin_soon", "awaiting_admin", now + timedelta(hours=2), 20),
    ]:
        seeded[name] = await seed_offer(
            db_session,
            user_id=customer,
            product_id=await stl(db_session),
            status=status,
            responds_by=responds_by,
            created_at=now - timedelta(hours=created_hours),
        )
    await mfa_admin(client, db_session)
    ids: list[str] = []
    cursor = None
    while True:
        params = {"user_id": str(customer), "limit": 3} | ({"cursor": cursor} if cursor else {})
        page = client.get(ADMIN_OFFERS, params=params).json()
        ids += [item["id"] for item in page["items"]]
        if (cursor := page["next_cursor"]) is None:
            break
    expected = [
        "admin_soon",
        "admin_late",
        "customer_soon",
        "customer_late",
        "accepted",
        "closed_old",
        "closed_new",
    ]
    assert ids == [str(seeded[name]) for name in expected]


async def test_queue_filters(client: TestClient, db_session: AsyncSession) -> None:
    customer = (await create_user(db_session)).id
    product = await stl(db_session)
    now = datetime.now(UTC)
    due = await seed_offer(
        db_session, user_id=customer, product_id=product, responds_by=now + timedelta(hours=1)
    )
    later = await seed_offer(
        db_session,
        user_id=customer,
        product_id=await stl(db_session),
        status="awaiting_customer",
        responds_by=now + timedelta(days=1),
    )
    closed = await seed_offer(
        db_session,
        user_id=customer,
        product_id=await stl(db_session),
        status="expired",
        responds_by=now - timedelta(days=1),
    )
    other = (await create_user(db_session)).id
    elsewhere = await seed_offer(db_session, user_id=other, product_id=product)
    await mfa_admin(client, db_session)

    def ids(**params: str) -> set[str]:
        return {i["id"] for i in client.get(ADMIN_OFFERS, params=params).json()["items"]}

    assert ids(user_id=str(customer)) == {str(due), str(later), str(closed)}
    assert ids(user_id=str(customer), status="awaiting_customer") == {str(later)}
    assert ids(product_id=str(product)) >= {str(due), str(elsewhere)}
    assert str(later) not in ids(product_id=str(product))
    bound = (now + timedelta(hours=2)).isoformat()
    assert ids(user_id=str(customer), responds_before=bound) == {str(due)}
    row = client.get(ADMIN_OFFERS, params={"user_id": str(other)}).json()["items"][0]
    assert row["customer"]["id"] == str(other) and "@" in row["customer"]["email"]


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "garbage"},
        {"cursor": _RANK_OUT_OF_RANGE},
        {"responds_before": "2026-10-20T00:00:00"},
        {"status": "pending"},
        {"limit": "0"},
    ],
    ids=["garbage", "rank-out-of-range", "naive-bound", "bad-status", "zero-limit"],
)
async def test_bad_query_is_422(
    client: TestClient, db_session: AsyncSession, params: dict[str, str]
) -> None:
    await mfa_admin(client, db_session)
    assert_problem(client.get(ADMIN_OFFERS, params=params), 422, "VALIDATION_ERROR")
