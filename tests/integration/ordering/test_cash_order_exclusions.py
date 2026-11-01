"""A cash order is never touched by the online payment machinery, its replay is a pure read,
and its amount due follows the live lines (VS-028 plan 6.2)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import app as main_app
from app.ordering.public import release_candidates
from app.payments.domain.exceptions import ManualReleaseRefusedError
from app.payments.infrastructure.payments import stale_live_query
from app.payments.public import (
    configured_payment_providers,
    reconcile_stuck,
    release_order_by_admin,
    release_stale,
)
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_refs
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    mfa_admin,
)
from tests.integration.ordering.checkout_support import checkout_body, shop_open  # noqa: F401
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    post,
    random_phone,
    setting,
    signed_in_buyer,
    stl,
    usd,
)
from tests.integration.payments.support import seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

ORDER_STATE = """
    SELECT o.status::text AS status, o.cancelled_at,
           (SELECT count(*) FROM order_status_history h WHERE h.order_id = o.id) AS history,
           (SELECT count(*) FROM order_items i WHERE i.order_id = o.id
              AND i.fulfillment_status = 'cancelled') AS cancelled_lines,
           (SELECT count(*) FROM payments p WHERE p.order_id = o.id) AS payments
    FROM orders o WHERE o.id = :o
"""


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


async def _state(engine: AsyncEngine, order_id: str) -> tuple[Any, ...]:
    async with engine.connect() as conn:
        return tuple((await conn.execute(text(ORDER_STATE), {"o": order_id})).one())


async def test_release_reconcile_retry_and_admin_release_never_select_a_cash_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, lamp)
        placed = post(client, pickup_body(random_phone()))
        assert placed.status_code == 201, placed.text
        order_id = placed.json()["order"]["id"]
        # Old enough for every job: only its shape can keep it out.
        old = datetime.now(UTC) - timedelta(days=3)
        await db_session.execute(
            text("UPDATE orders SET placed_at = :t WHERE id = :o"), {"t": old, "o": order_id}
        )
        await db_session.commit()
        before = await _state(db_engine, order_id)
        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        async with factory() as session:
            candidates = await release_candidates(
                session,
                placed_before=now,
                after=(old - timedelta(seconds=1), uuid.UUID(int=0)),
                limit=1000,
            )
        # The jobs' own providers, made and closed on this loop as the worker does: the app's
        # belong to the TestClient's loop, and a leftover live attempt from an earlier test
        # makes reconcile open the mock's Redis here, which the lifespan then cannot close.
        providers = configured_payment_providers(get_settings())
        try:
            await release_stale(
                factory,
                providers,
                now=now,
                start_after=(old - timedelta(seconds=1), uuid.UUID(int=0)),
            )
            await reconcile_stuck(factory, providers, now=now)
        finally:
            for provider in providers.values():
                await provider.aclose()
        retry = client.post(
            f"/api/v1/me/orders/{order_id}/payments",
            json={},
            headers=csrf(client) | {"Idempotency-Key": f"retry-{uuid.uuid4().hex}"},
        )
        admin = await create_user(db_session)
        async with factory() as session, session.begin():
            with pytest.raises(ManualReleaseRefusedError) as refused:
                await release_order_by_admin(
                    session,
                    uuid.UUID(order_id),
                    admin_id=admin.id,
                    reason="testing a cash order",
                    events_reviewed=True,
                    now=now,
                )
    assert str(order_id) not in {str(i) for _, i in candidates}
    assert_problem(retry, 409, "INVALID_STATE_TRANSITION")
    assert retry.json()["reason"] == "cash_order"
    assert refused.value.reason == "cash_order"
    assert await _state(db_engine, order_id) == before
    assert before[0] == "in_progress" and before[1] is None and before[4] == 0


async def test_a_replayed_cash_checkout_is_the_stored_response_and_a_pure_read(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp, owned = await physical(db_session, refs), await stl(db_session, refs)
    phone, key = random_phone(), f"key-{uuid.uuid4().hex}"
    statements: list[str] = []
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp, owned)
        await seed_online_order(
            db_session, user_id=user_id, stl_id=owned, line_status="awaiting_delivery"
        )
        first = post(client, pickup_body(phone), key)
        # The account now has an open cash order, so a new request would be refused. The
        # replay must not re-run that limit, take a lock or write anything.
        engine = main_app.state.db_engine.sync_engine

        def record(*args: Any) -> None:
            statements.append(" ".join(args[2].split()))

        event.listen(engine, "before_cursor_execute", record)
        try:
            replay = post(client, pickup_body(phone), key)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        add = client.post(
            "/api/v1/cart/items",
            json={"product_id": str(lamp), "quantity": 1},
            headers=csrf(client),
        )
        assert add.status_code == 200
        fresh = post(client, pickup_body(random_phone()))
    assert first.status_code == 201, first.text
    assert replay.status_code == 201 and replay.headers["idempotent-replayed"] == "true"
    assert replay.json() == first.json()
    assert replay.json()["dropped_lines"] == [{"product_id": str(owned), "reason": "already_owned"}]
    assert not any("pg_advisory" in s or "FOR UPDATE" in s for s in statements), statements
    assert not any(s.startswith(("INSERT INTO orders", "UPDATE", "DELETE")) for s in statements)
    assert_problem(fresh, 422, "CASH_NOT_AVAILABLE")


async def test_amount_due_follows_the_live_lines_and_is_null_when_nothing_is_due(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    a, b = (
        await physical(db_session, refs, price_cents=1500),
        await physical(db_session, refs, price_cents=700),
    )
    file = await stl(db_session, refs, price_cents=400)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, a, b)
        cash = post(client, pickup_body(random_phone())).json()["order"]
        add = client.post(
            "/api/v1/cart/items", json={"product_id": str(file)}, headers=csrf(client)
        )
        assert add.status_code == 200
        online = post(client, checkout_body(accept_digital_final_sale=True)).json()["order"]
        listing = client.get("/api/v1/me/orders").json()["items"]
        detail = client.get(f"/api/v1/me/orders/{cash['id']}").json()
        assert detail["amount_due"] == detail["total"] == usd(2200)
        await db_session.execute(
            text(
                "UPDATE order_items SET fulfillment_status = 'cancelled', cancelled_at = now()"
                " WHERE order_id = :o AND line_total_cents = 700"
            ),
            {"o": cash["id"]},
        )
        await db_session.commit()
        after = client.get(f"/api/v1/me/orders/{cash['id']}").json()
        online_detail = client.get(f"/api/v1/me/orders/{online['id']}").json()
        listing_after = {row["id"]: row for row in client.get("/api/v1/me/orders").json()["items"]}
    assert {row["id"]: row["amount_due"] for row in listing} == {
        cash["id"]: usd(2200),
        online["id"]: None,
    }
    assert after["amount_due"] == usd(1500) and after["total"] == usd(2200)
    assert listing_after[cash["id"]]["amount_due"] == usd(1500)
    assert online_detail["amount_due"] is None and online_detail["payment_due"] is False


async def test_admin_manual_release_over_http_is_409_cash_order_and_reconcile_never_selects_it(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, lamp)
        placed = post(client, pickup_body(random_phone()))
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["order"]["id"]
    before = await _state(db_engine, order_id)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        refused = admin.post(
            f"/api/v1/admin/orders/{order_id}/release",
            json={"reason": "testing a cash order", "events_reviewed": True},
            headers=csrf(admin),
        )
    assert_problem(refused, 409, "INVALID_STATE_TRANSITION")
    assert refused.json()["reason"] == "cash_order"
    assert await _state(db_engine, order_id) == before

    query = stale_live_query(before=datetime.now(UTC) + timedelta(days=1), after=None, limit=10_000)
    async with async_sessionmaker(db_engine)() as session:
        selected = [row.id for row in await session.execute(query)]
        cash = await session.scalar(
            text(
                "SELECT count(*) FROM payments WHERE id = ANY(:ids)"
                " AND (order_payment_method = 'cash' OR order_id = :o)"
            ),
            {"ids": selected, "o": order_id},
        )
    assert cash == 0
