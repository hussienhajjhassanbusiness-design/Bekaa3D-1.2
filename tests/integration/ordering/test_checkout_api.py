"""`POST /api/v1/checkout` up to a pending payment (VS-023 plan 6.2, Checkpoint 3).
Every refusal asserts what it left behind: no order, no payment, no claim, cart intact."""

import uuid
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.core.config import get_settings
from app.main import app as main_app
from app.payments.domain.exceptions import ProviderUnavailableError
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    Rows,
    add_to_cart,
    buyer,
    checkout_body,
    new_key,
    post_checkout,
    rows,
    set_price,
    shop_open,  # noqa: F401
)
from tests.integration.payments.support import seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]


async def _stl(db: AsyncSession, refs: Refs | None = None, **over: Any) -> uuid.UUID:
    product = await seed_product(
        db, refs or await seed_refs(db), type=ProductType.STL, **({"price_cents": 900} | over)
    )
    return product.id


def _untouched(cart_lines: int) -> Rows:
    return Rows(orders=0, lines=0, payments=0, claims=0, cart_lines=cart_lines, history=0)


# -------------------------------------------------------------- happy path


async def test_checkout_places_a_pending_order_at_the_live_price(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session, price_cents=900)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        response = post_checkout(client, checkout_body(customer_note="Thanks"))

    assert response.status_code == 201, response.text
    body = response.json()
    order, payment = body["order"], body["payment"]
    assert order["order_number"].startswith("B3D-") and len(order["order_number"]) == 12
    assert (order["status"], order["source"], order["payment_method"]) == (
        "pending_payment",
        "cart",
        "online",
    )
    assert order["fulfillment_method"] is None
    money = {"amount_cents": 900, "currency": "USD"}
    assert (order["subtotal"], order["total"]) == (money, money)
    assert order["tax"] == {"amount_cents": 0, "currency": "USD"}
    [line] = order["lines"]
    assert (line["product_id"], line["quantity"], line["fulfillment_status"]) == (
        str(stl),
        1,
        "pending",
    )
    assert line["unit_price"] == line["line_total"] == money
    assert (payment["status"], payment["provider"]) == ("pending", "mock")
    assert payment["redirect_url"].endswith(f"/checkout/return?order={order['order_number']}")
    assert body["dropped_lines"] == []
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)

    async with db_engine.connect() as conn:
        stored = (
            await conn.execute(
                text(
                    "SELECT o.customer_email_snapshot, o.customer_note, o.terms_accepted_at,"
                    " o.digital_terms_accepted_at, o.digital_terms_version,"
                    " o.cash_terms_accepted_at,"
                    " p.amount_cents, p.provider_payment_id, i.state, i.status_code,"
                    " i.resource_id"
                    " FROM orders o JOIN payments p ON p.order_id = o.id"
                    " JOIN idempotency_records i ON i.resource_id = o.id WHERE o.id = :o"
                ),
                {"o": order["id"]},
            )
        ).one()
        audit = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'order.placed' AND entity_id = :o"
            ),
            {"o": order["id"]},
        )
    assert stored.customer_email_snapshot == user.email
    assert stored.customer_note == "Thanks"
    assert stored.terms_accepted_at == stored.digital_terms_accepted_at is not None
    assert (stored.digital_terms_version, stored.cash_terms_accepted_at) == ("2026-10-17", None)
    assert stored.amount_cents == 900
    assert stored.provider_payment_id.startswith("mock_")
    assert (stored.state, stored.status_code) == ("done", 201)
    assert audit == 1


async def test_the_happy_path_stays_under_its_statement_ceiling(
    db_session: AsyncSession,
) -> None:
    """An N+1 over the cart's lines fails here (plan 5): three lines, fixed statements."""
    refs = await seed_refs(db_session)
    products = [await _stl(db_session, refs) for _ in range(3)]
    statements: list[str] = []
    with client_for(main_app) as client:
        await buyer(client, db_session, *products)
        engine = main_app.state.db_engine.sync_engine

        def count(*args: Any) -> None:
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", count)
        try:
            response = post_checkout(client)
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert response.status_code == 201, response.text
    print(f"\ncheckout statements (3 lines): {len(statements)}")
    assert len(statements) <= 30, statements


async def test_the_same_key_and_body_replays_the_stored_201(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session)
    key = new_key()
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        first = post_checkout(client, key=key)
        again = post_checkout(client, key=key)
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first.headers
    assert (await rows(db_engine, user.id)).orders == 1


async def test_the_same_key_with_a_different_body_conflicts(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session)
    key = new_key()
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        assert post_checkout(client, key=key).status_code == 201
        conflict = post_checkout(client, checkout_body(customer_note="other"), key=key)
    assert_problem(conflict, 409, "IDEMPOTENCY_KEY_CONFLICT")
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)


async def test_the_same_key_from_another_customer_is_independent(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    key = new_key()
    responses = []
    for _ in range(2):
        stl = await _stl(db_session, refs)
        with client_for(main_app) as client:
            await buyer(client, db_session, stl)
            responses.append(post_checkout(client, key=key))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["order"]["id"] != responses[1].json()["order"]["id"]


# -------------------------------------------------------- the cart's state


async def test_an_empty_or_missing_cart_is_409_cart_empty(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session)
    with client_for(main_app) as client:
        user = await buyer(client, db_session)
        no_cart = post_checkout(client)
        add_to_cart(client, stl)
        client.delete(f"/api/v1/cart/items/{stl}", headers=csrf(client))
        emptied = post_checkout(client)
    for response in (no_cart, emptied):
        assert_problem(response, 409, "CART_EMPTY")
        assert response.json()["dropped_lines"] == []
    assert await rows(db_engine, user.id) == _untouched(0)


async def test_lines_that_cannot_be_bought_are_422_naming_every_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    hidden = await _stl(db_session, refs)
    unavailable = await _stl(db_session, refs)
    whatsapp = (await seed_product(db_session, refs)).id
    over_cap = (await seed_product(db_session, refs)).id
    fine = await _stl(db_session, refs)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, hidden, unavailable, whatsapp, fine)
        add_to_cart(client, over_cap, 4)
        for sql, product in (
            ("is_visible = false", hidden),
            ("is_available = false", unavailable),
            ("purchase_mode = 'whatsapp_only'", whatsapp),
            ("max_quantity_per_line = 2", over_cap),
        ):
            await db_session.execute(
                text(f"UPDATE products SET {sql} WHERE id = :i"), {"i": product}
            )
        await db_session.commit()
        response = post_checkout(client)
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert sorted(response.json()["lines"], key=lambda line: line["reason"]) == [
        {"product_id": str(hidden), "reason": "not_listed"},
        {"product_id": str(over_cap), "reason": "over_cap", "max_quantity": 2},
        {"product_id": str(unavailable), "reason": "unavailable"},
        {"product_id": str(whatsapp), "reason": "whatsapp_only"},
    ]
    assert await rows(db_engine, user.id) == _untouched(5)


async def test_over_cap_lines_alone_are_422_quantity_exceeds_limit(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    first, second = (
        (await seed_product(db_session, refs)).id,
        (await seed_product(db_session, refs)).id,
    )
    with client_for(main_app) as client:
        user = await buyer(client, db_session)
        add_to_cart(client, first, 3)
        add_to_cart(client, second, 4)
        await db_session.execute(
            text("UPDATE products SET max_quantity_per_line = 2 WHERE id IN (:a, :b)"),
            {"a": first, "b": second},
        )
        await db_session.commit()
        response = post_checkout(client)
    assert_problem(response, 422, "QUANTITY_EXCEEDS_LIMIT")
    named = {line["product_id"]: line for line in response.json()["lines"]}
    assert named == {
        str(p): {"product_id": str(p), "reason": "over_cap", "max_quantity": 2}
        for p in (first, second)
    }
    assert await rows(db_engine, user.id) == _untouched(2)


async def test_an_stl_bought_since_it_was_added_is_dropped_and_named(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    owned, wanted = await _stl(db_session, refs), await _stl(db_session, refs, price_cents=700)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, owned, wanted)
        await seed_online_order(
            db_session, user_id=user.id, stl_id=owned, line_status="awaiting_delivery"
        )
        response = post_checkout(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["dropped_lines"] == [{"product_id": str(owned), "reason": "already_owned"}]
    assert [line["product_id"] for line in body["order"]["lines"]] == [str(wanted)]
    assert body["order"]["total"]["amount_cents"] == 700
    assert (await rows(db_engine, user.id)).cart_lines == 0


async def test_every_line_owned_is_409_cart_empty_naming_them(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    owned = await _stl(db_session)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, owned)
        await seed_online_order(db_session, user_id=user.id, stl_id=owned, line_status="delivered")
        response = post_checkout(client)
    assert_problem(response, 409, "CART_EMPTY")
    assert response.json()["dropped_lines"] == [
        {"product_id": str(owned), "reason": "already_owned"}
    ]
    counts = await rows(db_engine, user.id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 0, 0, 1)


# ------------------------------------------------------------ live price


async def test_a_changed_price_is_refused_with_the_new_price_and_nothing_is_charged(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The cart snapshot is display-only; a new live price is never charged silently."""
    stl = await _stl(db_session, price_cents=900)
    calls: list[object] = []
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        provider = main_app.state.payment_providers["mock"]
        create = provider.create_payment

        async def spy(request: object) -> object:
            calls.append(request)
            return await create(request)

        provider.create_payment = spy
        try:
            await set_price(db_session, stl, 1200)
            refused = post_checkout(client)
            refused_rows = await rows(db_engine, user.id)
            stale = post_checkout(
                client,
                checkout_body(
                    accepted_price_changes=[
                        {"product_id": str(stl), "amount_cents": 1100, "currency": "USD"}
                    ]
                ),
            )
            accepted = post_checkout(
                client,
                checkout_body(
                    accepted_price_changes=[
                        {"product_id": str(stl), "amount_cents": 1200, "currency": "USD"}
                    ]
                ),
            )
        finally:
            del provider.create_payment

    assert_problem(refused, 409, "CART_PRICE_CHANGED")
    change = {
        "product_id": str(stl),
        "old_amount_cents": 900,
        "new_amount_cents": 1200,
        "currency": "USD",
    }
    assert refused.json()["price_changes"] == [change]
    assert refused_rows == _untouched(1)
    assert_problem(stale, 409, "CART_PRICE_CHANGED")
    assert stale.json()["price_changes"] == [change]
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["order"]["total"]["amount_cents"] == 1200
    assert len(calls) == 1


# ------------------------------------------------- refusals before writing


async def test_no_online_provider_is_503_and_writes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stl = await _stl(db_session)
    monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    get_settings.cache_clear()
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        response = post_checkout(client)
    get_settings.cache_clear()
    assert_problem(response, 503, "ONLINE_PAYMENT_UNAVAILABLE")
    assert await rows(db_engine, user.id) == _untouched(1)


async def test_the_kill_switch_is_503_but_still_replays_an_earlier_success(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    first, second = await _stl(db_session, refs), await _stl(db_session, refs)
    key = new_key()
    with client_for(main_app) as client:
        user = await buyer(client, db_session, first)
        done = post_checkout(client, key=key)
        add_to_cart(client, second)
        await db_session.execute(
            text("UPDATE settings SET value = 'false' WHERE key = 'accepting_orders'")
        )
        await db_session.commit()
        try:
            paused = post_checkout(client)
            replayed = post_checkout(client, key=key)
        finally:
            await db_session.execute(
                text("UPDATE settings SET value = 'true' WHERE key = 'accepting_orders'")
            )
            await db_session.commit()
    assert_problem(paused, 503, "ORDERS_PAUSED")
    assert (replayed.status_code, replayed.json()) == (201, done.json())
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 1, 1)


@pytest.mark.parametrize(
    ("over", "code", "extension"),
    [
        (
            {"payment_method": "cash"},
            "PAYMENT_METHOD_NOT_ALLOWED",
            {"reason": "cash_requires_physical"},
        ),
        (
            {"payment_provider": "whish"},
            "PAYMENT_METHOD_NOT_ALLOWED",
            {"reason": "provider_not_configured"},
        ),
        ({"fulfillment_method": "pickup"}, "INVALID_FULFILLMENT", {}),
        ({"contact_phone": "+96170000000"}, "INVALID_FULFILLMENT", {}),
        ({"accept_digital_final_sale": None}, "VALIDATION_ERROR", {}),
        ({"total_cents": 1}, "VALIDATION_ERROR", {}),
        ({"accept_terms": False}, "VALIDATION_ERROR", {}),
    ],
    ids=["cash", "provider", "pickup", "phone", "consent", "client-total", "terms"],
)
async def test_a_refused_request_is_422_and_leaves_the_cart(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    over: dict[str, Any],
    code: str,
    extension: dict[str, Any],
) -> None:
    stl = await _stl(db_session)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        response = post_checkout(client, checkout_body(**over))
    assert_problem(response, 422, code)
    assert response.json().items() >= extension.items()
    assert await rows(db_engine, user.id) == _untouched(1)


async def test_a_physical_line_is_422_invalid_fulfillment(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    physical = (await seed_product(db_session, refs, purchase_mode=PurchaseMode.ONLINE_ONLY)).id
    with client_for(main_app) as client:
        user = await buyer(client, db_session, physical, await _stl(db_session, refs))
        response = post_checkout(client)
    assert_problem(response, 422, "INVALID_FULFILLMENT")
    assert await rows(db_engine, user.id) == _untouched(2)


@pytest.mark.parametrize("key", [None, "short", "has space in it", "x" * 256, "bad/slash1"])
async def test_a_missing_or_malformed_idempotency_key_is_422(
    db_session: AsyncSession, key: str | None
) -> None:
    stl = await _stl(db_session)
    with client_for(main_app) as client:
        await buyer(client, db_session, stl)
        headers = csrf(client) | ({"Idempotency-Key": key} if key is not None else {})
        response = client.post(CHECKOUT, json=checkout_body(), headers=headers)
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_the_session_boundary(db_session: AsyncSession) -> None:
    unverified = await create_user(db_session, verified=False)
    with client_for(main_app) as client:
        anonymous = client.post(
            CHECKOUT, json=checkout_body(), headers={"Idempotency-Key": new_key()}
        )
        login(client, unverified.email)
        not_verified = post_checkout(client)
        no_csrf = client.post(
            CHECKOUT, json=checkout_body(), headers={"Idempotency-Key": new_key()}
        )
    assert_problem(anonymous, 401)
    assert_problem(not_verified, 403, "EMAIL_VERIFICATION_REQUIRED")
    assert_problem(no_csrf, 403)


async def test_a_verified_buyer_without_the_csrf_header_is_403_and_writes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session)
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        response = client.post(
            CHECKOUT, json=checkout_body(), headers={"Idempotency-Key": new_key()}
        )
    assert_problem(response, 403, "CSRF_INVALID")
    assert await rows(db_engine, user.id) == _untouched(1)


# ---------------------------------------------------- inside the transaction


async def test_an_stl_held_by_the_customers_own_unpaid_order_is_409_not_500(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The ownership index is raced, not pre-checked: its violation maps to a domain 409."""
    stl = await _stl(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        user = await buyer(client, db_session, stl)
        await seed_online_order(db_session, user_id=user.id, stl_id=stl, line_status="pending")
        response = post_checkout(client)
    assert_problem(response, 409, "PRODUCT_ALREADY_OWNED")
    assert response.json()["product_ids"] == [str(stl)]
    counts = await rows(db_engine, user.id)
    assert (counts.orders, counts.payments, counts.claims, counts.cart_lines) == (1, 0, 0, 1)


async def test_an_stl_held_by_another_customers_unpaid_order_does_not_block(
    db_session: AsyncSession,
) -> None:
    stl = await _stl(db_session)
    other = await create_user(db_session)
    await seed_online_order(db_session, user_id=other.id, stl_id=stl, line_status="pending")
    with client_for(main_app) as client:
        await buyer(client, db_session, stl)
        assert post_checkout(client).status_code == 201


async def test_a_colliding_order_number_is_regenerated_in_a_savepoint(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    refs = await seed_refs(db_session)
    taken = f"B3D-{uuid.uuid4().hex[:8].upper()}"
    fresh = f"B3D-{uuid.uuid4().hex[:8].upper()}"
    holder = await create_user(db_session)
    await seed_online_order(
        db_session, user_id=holder.id, stl_id=await _stl(db_session, refs), order_number=taken
    )
    numbers = iter([taken, fresh])
    monkeypatch.setattr(
        "app.ordering.application.services.checkout.new_order_number", lambda: next(numbers)
    )
    with client_for(main_app) as client:
        user = await buyer(client, db_session, await _stl(db_session, refs))
        response = post_checkout(client)
    assert response.status_code == 201, response.text
    assert response.json()["order"]["order_number"] == fresh
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)


async def test_five_colliding_order_numbers_are_500_and_write_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    refs = await seed_refs(db_session)
    taken = f"B3D-{uuid.uuid4().hex[:8].upper()}"
    holder = await create_user(db_session)
    await seed_online_order(
        db_session, user_id=holder.id, stl_id=await _stl(db_session, refs), order_number=taken
    )
    drawn: list[str] = []

    def always_taken() -> str:
        drawn.append(taken)
        return taken

    monkeypatch.setattr("app.ordering.application.services.checkout.new_order_number", always_taken)
    with client_for(main_app, raise_server_exceptions=False) as client:
        user = await buyer(client, db_session, await _stl(db_session, refs))
        response = post_checkout(client)
    assert_problem(response, 500, "INTERNAL_ERROR")
    assert len(drawn) == 5
    assert await rows(db_engine, user.id) == _untouched(1)


# ------------------------------------------------------ after the commit


async def test_a_provider_failure_is_502_keeps_the_order_and_replays(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stl = await _stl(db_session)
    key = new_key()
    with client_for(main_app) as client:
        user = await buyer(client, db_session, stl)
        provider = main_app.state.payment_providers["mock"]

        async def down(request: object) -> object:
            raise ProviderUnavailableError("down")

        provider.create_payment = down
        try:
            failed = post_checkout(client, key=key)
            replayed = post_checkout(client, key=key)
        finally:
            del provider.create_payment
    assert_problem(failed, 502, "PAYMENT_PROVIDER_UNAVAILABLE")
    body = failed.json()
    assert body["order_number"].startswith("B3D-")
    assert_problem(replayed, 502, "PAYMENT_PROVIDER_UNAVAILABLE")
    assert replayed.headers["Idempotent-Replayed"] == "true"
    assert {k: v for k, v in replayed.json().items() if k != "request_id"} == {
        k: v for k, v in body.items() if k != "request_id"
    }
    async with db_engine.connect() as conn:
        state = (
            await conn.execute(
                text(
                    "SELECT o.status AS order_status, p.status AS payment_status, p.failed_at,"
                    " i.state, i.status_code FROM orders o JOIN payments p ON p.order_id = o.id"
                    " JOIN idempotency_records i ON i.resource_id = o.id WHERE o.id = :o"
                ),
                {"o": body["order_id"]},
            )
        ).one()
    assert (state.order_status, state.payment_status) == ("pending_payment", "failed")
    assert state.failed_at is not None
    assert (state.state, state.status_code) == ("done", 502)
    assert await rows(db_engine, user.id) == Rows(1, 1, 1, 1, 0, 1)
