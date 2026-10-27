"""VS-043 reports other than revenue (plan 6.2): recent purchases, best-selling STLs, top rated,
customer statistics, the overview, and no personal data in any body."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.reporting.api.admin_analytics import _encode_cursor
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import client_for, create_user, login, mfa_admin
from tests.integration.engagement.review_support import review_as
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.negotiation.offer_support import seed_offer, stl
from tests.integration.payments.refund_support import (
    create,
    ok,
    paid_cash,
    paid_online,
    payment_of,
)
from tests.integration.reporting.support import (
    BEIRUT,
    beirut_noon,
    body,
    free_day,
    paid_at,
    report,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

FAR = datetime(2099, 1, 1, tzinfo=UTC)
TOP = "ffffffff-ffff-ffff-ffff-ffffffffffff"


def _page(client: TestClient, cursor: str | None, limit: int = 20) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    return body(report(client, "recent-purchases", **params))


async def test_recent_purchases_page_by_keyset_without_duplicates_or_gaps(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    base = FAR + timedelta(days=uuid.uuid4().int % 300)
    mine: list[tuple[datetime, uuid.UUID]] = []
    for n in range(45):
        order = await paid_online(db_session, stl=None)
        moment = base - timedelta(minutes=n // 2)  # pairs share a verification time
        await paid_at(db_engine, order.order_id, moment)
        mine.append((moment, await payment_of(db_engine, order.order_id)))
    expected = [pid for _, pid in sorted(mine, key=lambda m: (m[0], m[1]), reverse=True)]
    start = _encode_cursor(base + timedelta(microseconds=1), uuid.UUID(TOP))
    seen: list[str] = []
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        cursor: str | None = start
        while len(seen) < 45:
            page = _page(client, cursor)
            seen += [item["order_id"] for item in page["items"]]
            cursor = page["next_cursor"]
            assert cursor is not None or len(seen) >= 45
        assert report(client, "recent-purchases", cursor="not-a-cursor").status_code == 422
    async with db_engine.connect() as conn:
        orders = {
            row.id: str(row.order_id)
            for row in await conn.execute(
                text("SELECT id, order_id FROM payments WHERE id = ANY(:ids)"),
                {"ids": expected},
            )
        }
    assert seen[:45] == [orders[pid] for pid in expected]
    assert len(set(seen[:45])) == 45


async def test_a_cash_order_appears_at_its_handover_and_an_unpaid_one_never(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    unpaid = await seed_physical_order(db_session, payment_method="cash", line_states=("pending",))
    order = await paid_cash(db_session)
    handover = FAR - timedelta(days=400, microseconds=uuid.uuid4().int % 10**6)
    await paid_at(db_engine, order.order_id, handover)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        page = _page(client, _encode_cursor(handover + timedelta(microseconds=1), uuid.UUID(TOP)))
    first = page["items"][0]
    assert first["order_id"] == str(order.order_id)
    assert datetime.fromisoformat(first["paid_at"]) == handover
    assert first["payment_method"] == "cash"
    assert (first["net_cents"], first["paid_lines"]) == (1000, 1)
    assert str(unpaid.order_id) not in {item["order_id"] for item in page["items"]}


async def _stl_order(db: AsyncSession, engine: AsyncEngine, product: uuid.UUID, state: str) -> Any:
    order = await paid_online(db, physical=("delivered",), stl=state)
    await db.execute(
        text("UPDATE order_items SET product_id = :p WHERE id = :i"),
        {"p": product, "i": order.stl},
    )
    await db.commit()
    return order


async def test_stl_sales_rank_owned_lines_with_todays_label_and_awaiting_counts(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    refs = await seed_refs(db_session)
    a = await seed_product(db_session, refs, type=ProductType.STL)
    b = await seed_product(db_session, refs, type=ProductType.STL)
    c = await seed_product(db_session, refs, type=ProductType.STL)
    orders = [
        await _stl_order(db_session, db_engine, a.id, "delivered"),
        await _stl_order(db_session, db_engine, a.id, "awaiting_delivery"),
        await _stl_order(db_session, db_engine, b.id, "awaiting_delivery"),
        await _stl_order(db_session, db_engine, c.id, "delivered"),
    ]
    for order in orders:
        await paid_at(db_engine, order.order_id, beirut_noon(day))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ok(create(client, orders[2].order_id, [(orders[2].stl, 200)]), 201)
        ok(create(client, orders[3].order_id, [(orders[3].stl, 500)]), 201)
        found = body(report(client, "stl-sales", from_=day, to=day, limit=10))
    items = [(i["product_id"], i["units"], i["lines"], i["net_cents"]) for i in found["items"]]
    assert items == [(str(a.id), 2, 2, 1000), (str(b.id), 1, 1, 300)]
    assert found["items"][0]["name"] == a.name
    assert found["items"][0]["slug"] == a.slug
    assert [i["awaiting_delivery"] for i in found["items"]] == [1, 1]
    assert found["stl_lines_awaiting_delivery"] >= 2


async def _rated(db: AsyncSession, rating: str, count: int, **state: Any) -> uuid.UUID:
    product = (await seed_product(db, await seed_refs(db))).id
    sets = ", ".join(f"{column} = :{column}" for column in state)
    await db.execute(
        text(
            "UPDATE products SET average_rating = :r, review_count = :n"
            + (f", {sets}" if sets else "")
            + " WHERE id = :p"
        ),
        {"r": Decimal(rating), "n": count, "p": product} | state,
    )
    await db.commit()
    return product


async def test_top_rated_reads_the_aggregates_excludes_deleted_and_flags_hidden(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    floor = 980 + uuid.uuid4().int % 10  # under the 1000 bound; no other test seeds as many
    best = await _rated(db_session, "4.90", floor + 5)
    tie = await _rated(db_session, "4.50", floor + 9)
    lower = await _rated(db_session, "4.50", floor + 1, is_visible=False)
    gone = await _rated(db_session, "5.00", floor + 9, deleted_at=datetime.now(UTC))
    few = await _rated(db_session, "5.00", floor - 1)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        found = body(report(client, "top-rated-products", min_reviews=floor, limit=100))
        assert report(client, "top-rated-products", min_reviews=0).status_code == 422
    ours = [i for i in found["items"] if i["product_id"] in {str(p) for p in (best, tie, lower)}]
    assert [i["product_id"] for i in ours] == [str(best), str(tie), str(lower)]
    assert [i["is_visible"] for i in ours] == [True, True, False]
    assert Decimal(ours[0]["average_rating"]) == Decimal("4.90")
    ids = {i["product_id"] for i in found["items"]}
    assert str(gone) not in ids and str(few) not in ids


async def test_top_rated_drops_a_review_hidden_through_moderation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await stl(db_session)
    reviews = []
    for rating in (5, 5, 1):
        buyer = await create_user(db_session)
        reviews.append((await review_as(db_session, buyer.id, product, rating))["id"])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        before = _rating_of(client, product)
        hidden = client.post(
            f"/api/v1/admin/reviews/{reviews[2]}/hide",
            json={},
            headers={"X-CSRF-Token": client.cookies.get("csrf_token") or ""},
        )
        assert hidden.status_code == 200, hidden.text
        after = _rating_of(client, product)
    assert (Decimal(before["average_rating"]), before["review_count"]) == (Decimal("3.67"), 3)
    assert (Decimal(after["average_rating"]), after["review_count"]) == (Decimal("5.00"), 2)


def _rating_of(client: TestClient, product: uuid.UUID) -> dict[str, Any]:
    found = body(report(client, "top-rated-products", min_reviews=2, limit=100))
    rows = [i for i in found["items"] if i["product_id"] == str(product)]
    if rows:
        return rows[0]
    raise AssertionError("the product is not among the top 100; raise its rating")


async def test_customer_statistics(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    day = await free_day(db_engine)
    repeat = (await create_user(db_session)).id
    for _ in range(2):
        order = await seed_physical_order(
            db_session,
            payment_method="online",
            payment_status="paid",
            line_states=("delivered",),
            user_id=repeat,
        )
        await paid_at(db_engine, order.order_id, beirut_noon(day))
    once = await paid_online(db_session, stl=None)
    await paid_at(db_engine, once.order_id, beirut_noon(day))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        ranged = body(report(client, "customers", from_=day, to=day))
        today = datetime.now(BEIRUT).date()
        before = body(report(client, "customers", from_=today - timedelta(days=1), to=today))
        await create_user(db_session)
        await create_user(db_session, verified=False)
        await create_user(db_session, role=UserRole.ADMIN)
        gone = await create_user(db_session)
        await db_session.execute(
            text("UPDATE users SET anonymized_at = now() WHERE id = :u"), {"u": gone.id}
        )
        await db_session.commit()
        after = body(report(client, "customers", from_=today - timedelta(days=1), to=today))
    assert (ranged["buyers"], ranged["repeat_buyers"]) == (2, 1)
    assert ranged["net_per_buyer_cents"] == 3000 // 2
    assert after["registered_customers"] - before["registered_customers"] == 1
    assert after["new_customers"] - before["new_customers"] == 1


async def test_overview_counts_live_offers_by_status_and_awaiting_stl_lines(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    order = await paid_online(db_session)
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        before = body(report(client, "overview", from_=day, to=day))
        for status in ("awaiting_admin", "awaiting_customer", "accepted", "expired", "paid"):
            buyer = (await create_user(db_session)).id
            await seed_offer(
                db_session, user_id=buyer, product_id=await stl(db_session), status=status
            )
        await paid_online(db_session)  # one more STL line awaiting delivery, paid now
        after = body(report(client, "overview", from_=day, to=day))
    offers = {
        k: after["pending_offers"][k] - before["pending_offers"][k] for k in after["pending_offers"]
    }
    assert offers == {"awaiting_admin": 1, "awaiting_customer": 1, "accepted": 1, "total": 3}
    assert after["stl_lines_awaiting_delivery"] - before["stl_lines_awaiting_delivery"] == 1
    assert after["net"] == {"physical_cents": 1000, "stl_cents": 500, "total_cents": 1500}
    assert (after["paid_orders"], after["buyers"], after["new_customers"]) == (1, 1, 0)


async def test_no_response_carries_personal_data(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    day = await free_day(db_engine)
    email = f"pii-{uuid.uuid4().hex}@example.com"
    buyer = await create_user(db_session, email=email)
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=("delivered",),
        user_id=buyer.id,
        email=email,
    )
    await paid_at(db_engine, order.order_id, beirut_noon(day))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        bodies = [
            report(client, path, from_=day, to=day).text
            for path in ("revenue", "overview", "customers", "stl-sales")
        ]
        bodies += [
            report(client, "top-rated-products").text,
            report(client, "recent-purchases", limit=100).text,
        ]
    for raw in bodies:
        assert email not in raw and order.phone not in raw
        _no_keys(json.loads(raw), {"email", "phone", "address", "name_snapshot", "recipient_name"})


def _no_keys(found: Any, banned: set[str]) -> None:
    if isinstance(found, dict):
        assert not banned & set(found), found.keys()
        for value in found.values():
            _no_keys(value, banned)
    elif isinstance(found, list):
        for value in found:
            _no_keys(value, banned)


async def test_a_customer_gets_the_imaginary_paths_404_and_anonymous_gets_401(
    db_session: AsyncSession,
) -> None:
    customer = await create_user(db_session)
    with client_for(main_app) as client:
        assert report(client, "revenue").status_code == 401
        login(client, customer.email)
        real = report(client, "revenue")
        imaginary = client.get("/api/v1/admin/definitely-not-a-route")
    assert real.status_code == imaginary.status_code == 404
    strip = ("request_id", "instance")
    assert {k: v for k, v in real.json().items() if k not in strip} == {
        k: v for k, v in imaginary.json().items() if k not in strip
    }
