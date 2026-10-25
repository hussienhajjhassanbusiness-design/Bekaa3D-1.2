"""Physical and cash checkout (VS-028 plan 6.2). Every refusal asserts nothing was created."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.security import hash_phone
from app.main import app as main_app
from app.ordering.domain.fulfillment import DELIVERY_FEE_NOTE
from app.ordering.infrastructure.notices import SqlOrderNotices
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.ordering.checkout_support import (
    Rows,
    add_to_cart,
    checkout_body,
    new_key,
    rows,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    cash_body,
    delivery_body,
    physical,
    pickup_body,
    post,
    random_phone,
    seed_address,
    seed_block,
    seed_cash_order,
    setting,
    signed_in_buyer,
    spaced,
    stl,
)
from tests.integration.payments.support import seed_online_order
from tests.integration.payments.verification_support import (
    WEBHOOK,
    mock_fixture,  # noqa: F401
    signed,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

PICKUP_ADDRESS = "Workshop, Zahle"


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", PICKUP_ADDRESS):
        yield


CASH_NOT_AVAILABLE = "Cash on delivery isn't available for this order; please pay online."


def assert_cash_not_available(response: Any) -> None:
    """No `reason`, and one detail for a block and for an open order (ADR-038)."""
    assert_problem(response, 422, "CASH_NOT_AVAILABLE")
    assert "reason" not in response.json()
    assert response.json()["detail"] == CASH_NOT_AVAILABLE


def untouched(cart_lines: int) -> Rows:
    return Rows(orders=0, lines=0, payments=0, claims=0, cart_lines=cart_lines, history=0)


async def side_effects(engine: AsyncEngine, user_id: uuid.UUID) -> tuple[int, int, int]:
    """The cash email, the notification and the `order.placed` audit row."""
    sql = """
        SELECT
          (SELECT count(*) FROM email_outbox WHERE user_id = :u),
          (SELECT count(*) FROM notifications WHERE user_id = :u),
          (SELECT count(*) FROM audit_logs WHERE actor_user_id = :u AND action = 'order.placed')
    """
    async with engine.connect() as conn:
        a, b, c = (await conn.execute(text(sql), {"u": user_id})).one()
    return a, b, c


async def order_row(engine: AsyncEngine, order_id: str) -> Any:
    sql = "SELECT * FROM orders WHERE id = :i"
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), {"i": order_id})).one()


# ------------------------------------------------ end to end per cart type


async def test_a_physical_delivery_online_keeps_lines_pending_and_totals_add_up(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session, price_cents=1000)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        phone = random_phone()
        address = await seed_address(db_session, user_id, phone)
        response = post(
            client, checkout_body(fulfillment_method="delivery", address_id=str(address))
        )
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    assert (order["status"], order["payment_method"]) == ("pending_payment", "online")
    assert order["fulfillment_method"] == "delivery"
    assert order["total"] == order["subtotal"] and order["tax"]["amount_cents"] == 0
    assert order["delivery_address"]["recipient_name"] == "Rita Customer"
    assert order["delivery_fee_note"] and order["estimated_dispatch_at"]
    assert response.json()["payment"]["provider"] == "mock"
    assert "contact_phone" not in order and phone[4:] not in response.text
    stored = await order_row(db_engine, order["id"])
    assert stored.contact_phone_snapshot == phone
    assert stored.contact_phone_hash == hash_phone(phone)


async def test_a_physical_pickup_online_and_a_mixed_cart_online(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp, file = await physical(db_session, refs), await stl(db_session, refs)
    with client_for(main_app) as client:
        user = await signed_in_buyer(client, db_session, lamp)
        pickup = post(
            client,
            checkout_body(fulfillment_method="pickup", contact_phone=spaced(random_phone())),
        )
        add_to_cart(client, lamp)
        add_to_cart(client, file)
        mixed = post(
            client,
            checkout_body(fulfillment_method="pickup", contact_phone=random_phone()),
        )
    assert pickup.status_code == mixed.status_code == 201, (pickup.text, mixed.text)
    assert pickup.json()["order"]["delivery_fee_note"] is None
    lines = {x["product_type"]: x["fulfillment_status"] for x in mixed.json()["order"]["lines"]}
    assert lines == {"physical": "pending", "stl": "pending"}
    assert mixed.json()["order"]["total"]["amount_cents"] == 1900
    assert await rows(db_engine, user) == Rows(2, 3, 2, 2, 0, 2)


async def test_a_mixed_delivery_order_paid_online_moves_only_the_stl_line(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """Verification sends the STL to the delivery queue; the physical line waits for printing,
    and the confirmation email carries the courier note and the dispatch estimate."""
    refs = await seed_refs(db_session)
    lamp, file = await physical(db_session, refs), await stl(db_session, refs)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp, file)
        address = await seed_address(db_session, user_id)
        placed = post(client, checkout_body(fulfillment_method="delivery", address_id=str(address)))
        assert placed.status_code == 201, placed.text
        payment_id = placed.json()["payment"]["id"]
        await mock.simulate(uuid.UUID(payment_id), "paid")
        event = {"event_id": f"ev_{uuid.uuid4().hex}", "payment_reference": payment_id}
        raw = json.dumps(event | {"type": "payment"}).encode()
        assert client.post(WEBHOOK, content=raw, headers=signed(raw)).status_code == 200
    order_id = placed.json()["order"]["id"]
    stored = await order_row(db_engine, order_id)
    async with db_engine.connect() as conn:
        lines = await conn.execute(
            text(
                "SELECT product_type::text, fulfillment_status::text FROM order_items"
                " WHERE order_id = :o"
            ),
            {"o": order_id},
        )
        emails = await conn.scalars(
            text(
                "SELECT payload FROM email_outbox WHERE template = 'order_payment_confirmed'"
                " AND payload->>'order_id' = :o"
            ),
            {"o": order_id},
        )
        states: dict[str, str] = dict(lines.all())
        payloads = emails.all()
    assert stored.status == "in_progress"
    assert states == {"stl": "awaiting_delivery", "physical": "pending"}
    assert len(payloads) == 1
    assert payloads[0]["fulfillment_method"] == "delivery"
    assert payloads[0]["delivery_fee_note"] == DELIVERY_FEE_NOTE
    eta = payloads[0]["estimated_dispatch_at"]
    assert stored.estimated_dispatch_at is not None
    assert datetime.fromisoformat(eta) == stored.estimated_dispatch_at


async def test_cash_is_refused_for_an_stl_only_and_a_mixed_cart_before_any_lock(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp, file = await physical(db_session, refs), await stl(db_session, refs)
    statements: list[str] = []
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, file)
        only_stl = post(client, cash_body())
        add_to_cart(client, lamp)
        engine = main_app.state.db_engine.sync_engine

        def record(*args: Any) -> None:
            statements.append(args[2])

        event.listen(engine, "before_cursor_execute", record)
        try:
            mixed = post(client, pickup_body(random_phone()))
        finally:
            event.remove(engine, "before_cursor_execute", record)
    for response in (only_stl, mixed):
        assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
        assert response.json()["reason"] == "cash_requires_physical"
    assert not any("pg_advisory" in s for s in statements)
    assert await rows(db_engine, user_id) == untouched(2)


# --------------------------------------------------------------- cash order


@pytest.mark.parametrize("method", ["delivery", "pickup"])
async def test_a_cash_order_is_one_transaction_with_no_payment_and_no_provider_call(
    db_engine: AsyncEngine, db_session: AsyncSession, method: str
) -> None:
    lamp = await physical(db_session, price_cents=1250)
    phone = random_phone()
    calls: list[object] = []
    with client_for(main_app) as client:
        provider = main_app.state.payment_providers["mock"]
        original = provider.create_payment

        async def spy(request: object) -> object:
            calls.append(request)
            return await original(request)

        provider.create_payment = spy
        try:
            user_id = await signed_in_buyer(client, db_session, lamp)
            body = (
                delivery_body(await seed_address(db_session, user_id, phone))
                if method == "delivery"
                else pickup_body(spaced(phone))
            )
            response = post(client, body)
        finally:
            provider.create_payment = original
    assert response.status_code == 201, response.text
    body = response.json()
    order = body["order"]
    assert body["payment"] is None and calls == []
    assert (order["status"], order["payment_method"], order["payment_due"]) == (
        "in_progress",
        "cash",
        True,
    )
    assert order["amount_due"] == order["total"] == {"amount_cents": 1250, "currency": "USD"}
    assert order["lines"][0]["fulfillment_status"] == "pending"
    assert await rows(db_engine, user_id) == Rows(1, 1, 0, 1, 0, 1)
    stored = await order_row(db_engine, order["id"])
    assert stored.cash_terms_accepted_at is not None
    assert (stored.contact_phone_snapshot, stored.contact_phone_hash) == (
        phone,
        hash_phone(phone),
    )
    assert stored.estimated_dispatch_at is not None
    async with db_engine.connect() as conn:
        claim = (
            await conn.execute(
                text("SELECT state, status_code FROM idempotency_records WHERE user_id = :u"),
                {"u": user_id},
            )
        ).one()
        outbox = await conn.scalar(
            text(
                "SELECT count(*) FROM email_outbox WHERE template = 'order_cash_placed'"
                " AND user_id = :u"
            ),
            {"u": user_id},
        )
        notices = await conn.scalar(
            text("SELECT count(*) FROM notifications WHERE user_id = :u"), {"u": user_id}
        )
    assert tuple(claim) == ("done", 201) and outbox == 1 and notices == 1


async def test_the_dispatch_estimate_uses_the_longest_lead_over_the_batches(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Seeded products have lead 3 and batch 2: 5 units = 3 batches = 9 days."""
    lamp = await physical(db_session, max_quantity_per_line=5)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session)
        add_to_cart(client, lamp, 5)
        response = post(client, pickup_body(random_phone()))
    order = response.json()["order"]
    stored = await order_row(db_engine, order["id"])
    assert (stored.estimated_dispatch_at - stored.placed_at).days == 9
    async with db_engine.connect() as conn:
        snapshot = (
            await conn.execute(
                text(
                    "SELECT lead_time_days_snapshot, batch_size_snapshot FROM order_items"
                    " WHERE order_id = :o"
                ),
                {"o": order["id"]},
            )
        ).one()
    assert tuple(snapshot) == (3, 2)


async def test_an_order_total_equals_the_sum_of_its_lines_on_cash_and_mixed_orders(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    a, b = (
        await physical(db_session, refs, price_cents=1100),
        await physical(db_session, refs, price_cents=2300),
    )
    file = await stl(db_session, refs, price_cents=700)
    with client_for(main_app) as client:
        await signed_in_buyer(client, db_session, a, b)
        add_to_cart(client, a, 1)  # adds to the 1 already there: 2 x a, 1 x b
        cash = post(client, pickup_body(random_phone()))
        add_to_cart(client, a, 3)
        add_to_cart(client, b)
        add_to_cart(client, file)
        mixed = post(
            client, checkout_body(fulfillment_method="pickup", contact_phone=random_phone())
        )
    for response, expected in ((cash, 2 * 1100 + 2300), (mixed, 3 * 1100 + 2300 + 700)):
        assert response.status_code == 201, response.text
        async with db_engine.connect() as conn:
            lines = await conn.scalar(
                text("SELECT sum(line_total_cents) FROM order_items WHERE order_id = :o"),
                {"o": response.json()["order"]["id"]},
            )
            order = await conn.scalar(
                text("SELECT total_cents FROM orders WHERE id = :o"),
                {"o": response.json()["order"]["id"]},
            )
        assert lines == order == expected


async def test_cash_works_with_no_provider_but_online_is_503(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    lamp = await physical(db_session)
    monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    get_settings.cache_clear()
    try:
        with client_for(main_app) as client:
            user_id = await signed_in_buyer(client, db_session, lamp)
            online = post(
                client, checkout_body(fulfillment_method="pickup", contact_phone=random_phone())
            )
            cash = post(client, pickup_body(random_phone()))
    finally:
        get_settings.cache_clear()
    assert_problem(online, 503, "ONLINE_PAYMENT_UNAVAILABLE")
    assert cash.status_code == 201, cash.text
    assert (await rows(db_engine, user_id)).payments == 0


# ----------------------------------------------------------- cash limits


async def refused_cash(
    client: Any, db_engine: AsyncEngine, user_id: uuid.UUID, body: dict[str, Any], **headers: str
) -> Any:
    before = await rows(db_engine, user_id)
    response = post(client, body, **headers)
    after = await rows(db_engine, user_id)
    assert (after.orders, after.lines, after.payments, after.claims, after.history) == (
        before.orders,
        before.lines,
        before.payments,
        before.claims,
        before.history,
    )
    assert after.cart_lines == before.cart_lines
    return response


async def test_the_cash_switch_off_refuses_and_creates_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    async with setting(db_engine, "cash_payment_enabled", False):
        with client_for(main_app) as client:
            user_id = await signed_in_buyer(client, db_session, lamp)
            response = await refused_cash(client, db_engine, user_id, pickup_body(random_phone()))
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert response.json()["reason"] == "cash_disabled"


async def test_a_zero_total_is_refused_for_cash(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    free = await physical(db_session, price_cents=0)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, free)
        response = await refused_cash(client, db_engine, user_id, pickup_body(random_phone()))
    assert_problem(response, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert response.json()["reason"] == "zero_total"


async def test_the_total_cap_is_checked_on_the_live_total(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session, price_cents=10_000)
    async with setting(
        db_engine, "cash_max_order_total", {"amount_cents": 10_000, "currency": "USD"}
    ):
        with client_for(main_app) as client:
            user_id = await signed_in_buyer(client, db_session, lamp)
            await db_session.execute(
                text("UPDATE products SET price_cents = 10001 WHERE id = :i"), {"i": lamp}
            )
            await db_session.commit()
            over = await refused_cash(
                client,
                db_engine,
                user_id,
                pickup_body(
                    random_phone(),
                    accepted_price_changes=[
                        {"product_id": str(lamp), "amount_cents": 10001, "currency": "USD"}
                    ],
                ),
            )
            await db_session.execute(
                text("UPDATE products SET price_cents = 10000 WHERE id = :i"), {"i": lamp}
            )
            await db_session.commit()
            at_cap = post(
                client,
                pickup_body(
                    random_phone(),
                    accepted_price_changes=[
                        {"product_id": str(lamp), "amount_cents": 10000, "currency": "USD"}
                    ],
                ),
            )
    assert_problem(over, 422, "CASH_PAYMENT_LIMIT_REACHED")
    assert over.json()["reason"] == "order_total"
    assert at_cap.status_code == 201, at_cap.text


async def test_an_over_cap_total_reads_the_same_whether_or_not_the_phone_is_blocked(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The cap needs no phone, so it runs first and cannot tell a probe about one."""
    lamp = await physical(db_session, price_cents=10_001)
    blocked_phone = random_phone()
    await seed_block(db_session, (await create_user(db_session)).id, blocked_phone)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        responses = [
            await refused_cash(client, db_engine, user_id, pickup_body(phone))
            for phone in (blocked_phone, random_phone())
        ]
    for response in responses:
        assert_problem(response, 422, "CASH_PAYMENT_LIMIT_REACHED")
        assert response.json()["reason"] == "order_total"


async def test_a_second_open_cash_order_is_refused_by_account_and_by_phone(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    shared = random_phone()
    with client_for(main_app) as client:
        first = await signed_in_buyer(client, db_session, lamp)
        done = post(client, pickup_body(shared))
        add_to_cart(client, lamp)
        same_account = await refused_cash(client, db_engine, first, pickup_body(random_phone()))
    with client_for(main_app) as other:
        second = await signed_in_buyer(other, db_session, lamp)
        same_phone = await refused_cash(other, db_engine, second, pickup_body(spaced(shared)))
    assert done.status_code == 201
    for response in (same_account, same_phone):
        assert_cash_not_available(response)


async def test_blocks_match_by_account_and_by_phone_and_cleared_blocks_do_not(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    blocked_phone = random_phone()
    other = await create_user(db_session)
    await seed_block(db_session, other.id, blocked_phone)
    with client_for(main_app) as client:
        by_phone = await signed_in_buyer(client, db_session, lamp)
        phone_refusal = await refused_cash(
            client, db_engine, by_phone, pickup_body(spaced(blocked_phone))
        )
    with client_for(main_app) as client:
        user = await create_user(db_session)
        login(client, user.email)
        add_to_cart(client, lamp)
        await seed_block(db_session, user.id, random_phone())
        by_user = await refused_cash(client, db_engine, user.id, pickup_body(random_phone()))
        await db_session.execute(
            text(
                "UPDATE cash_payment_blocks SET cleared_at = now(), cleared_by = :a"
                " WHERE user_id = :u"
            ),
            {"u": user.id, "a": (await create_user(db_session)).id},
        )
        await db_session.commit()
        cleared = post(client, pickup_body(random_phone()))
    for response in (phone_refusal, by_user):
        assert_cash_not_available(response)
    assert cleared.status_code == 201, cleared.text


async def test_a_cart_with_a_free_physical_line_is_refused_cash_but_can_pay_online(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-043 d12: a refusal leaving only a $0 line would end with `other` and escape the
    BR-144 block, so cash refuses the cart outright, with the one generic refusal."""
    lamp, free = await physical(db_session), await physical(db_session, price_cents=0)
    with client_for(main_app) as client:
        buyer = await signed_in_buyer(client, db_session, lamp, free)
        refused = await refused_cash(client, db_engine, buyer, pickup_body(random_phone()))
        online = post(
            client, checkout_body(fulfillment_method="pickup", contact_phone=random_phone())
        )
    assert_cash_not_available(refused)
    assert online.status_code == 201, online.text


async def test_block_and_open_order_refusals_by_account_or_phone_are_byte_identical(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The caller cannot tell a block from an open order, nor the account from the phone."""
    lamp = await physical(db_session)
    request_id = "req-vs028-indistinguishable"
    phone_a, phone_b = random_phone(), random_phone()
    bodies: dict[str, Any] = {}
    # blocked: A by user_id, B only by a phone match
    owner = await create_user(db_session)
    await seed_block(db_session, owner.id, phone_b)
    with client_for(main_app) as client:
        a = await signed_in_buyer(client, db_session, lamp)
        await seed_block(db_session, a, random_phone())
        bodies["blocked_a"] = await refused_cash(
            client, db_engine, a, pickup_body(phone_a), **{"X-Request-ID": request_id}
        )
    with client_for(main_app) as client:
        b = await signed_in_buyer(client, db_session, lamp)
        bodies["blocked_b"] = await refused_cash(
            client, db_engine, b, pickup_body(phone_b), **{"X-Request-ID": request_id}
        )
    # open_orders: A with their own open order, B matching another account's by phone
    holder, held_phone = await create_user(db_session), random_phone()
    await seed_cash_order(db_session, holder.id, held_phone)
    with client_for(main_app) as client:
        c = await signed_in_buyer(client, db_session, lamp)
        await seed_cash_order(db_session, c, random_phone())
        bodies["open_a"] = await refused_cash(
            client, db_engine, c, pickup_body(random_phone()), **{"X-Request-ID": request_id}
        )
    with client_for(main_app) as client:
        d = await signed_in_buyer(client, db_session, lamp)
        bodies["open_b"] = await refused_cash(
            client, db_engine, d, pickup_body(held_phone), **{"X-Request-ID": request_id}
        )
    first = bodies["blocked_a"]
    assert_cash_not_available(first)
    assert request_id in first.text
    for other in ("blocked_b", "open_a", "open_b"):
        assert bodies[other].status_code == 422
        assert bodies[other].headers["content-type"] == first.headers["content-type"]
        assert bodies[other].content == first.content, other


async def test_one_phone_in_three_spellings_matches_one_block_and_one_open_count(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    phone = random_phone()
    national = "0" + phone[4:]
    holder = await create_user(db_session)
    await seed_cash_order(db_session, holder.id, phone)
    refusals = []
    for spelling in (phone, spaced(phone), national):
        with client_for(main_app) as client:
            user_id = await signed_in_buyer(client, db_session, lamp)
            refusals.append(await refused_cash(client, db_engine, user_id, pickup_body(spelling)))
    for response in refusals:
        assert_cash_not_available(response)


@pytest.mark.parametrize(
    ("status", "line_status"), [("cancelled", "cancelled"), ("completed", "delivered")]
)
async def test_an_order_that_is_no_longer_open_frees_the_limit(
    db_engine: AsyncEngine, db_session: AsyncSession, status: str, line_status: str
) -> None:
    lamp = await physical(db_session)
    phone = random_phone()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        await seed_cash_order(db_session, user_id, phone, status=status, line_status=line_status)
        response = post(client, pickup_body(phone))
    assert response.status_code == 201, response.text


# ------------------------------------------------------- cash transaction


async def test_a_paused_shop_refuses_cash_with_503_and_writes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        address = await seed_address(db_session, user_id)
        async with setting(db_engine, "accepting_orders", False):
            responses = [
                await refused_cash(client, db_engine, user_id, body)
                for body in (pickup_body(random_phone()), delivery_body(address))
            ]
    for response in responses:
        assert_problem(response, 503, "ORDERS_PAUSED")
    assert await rows(db_engine, user_id) == untouched(1)
    assert await side_effects(db_engine, user_id) == (0, 0, 0)


async def test_a_failure_after_the_order_insert_leaves_no_order_no_claim_and_the_cart(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last write before the cart is cleared fails: one transaction, so nothing stays,
    and the same key then places the order."""
    lamp = await physical(db_session)
    phone, key = random_phone(), new_key()

    async def broken(*args: Any) -> None:
        raise RuntimeError("forced after the order insert")

    monkeypatch.setattr(SqlOrderNotices, "cash_order_placed", broken)
    with client_for(main_app, raise_server_exceptions=False) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        failed = post(client, pickup_body(phone), key)
        after_failure = (await rows(db_engine, user_id), await side_effects(db_engine, user_id))
        monkeypatch.undo()
        retried = post(client, pickup_body(phone), key)
    assert_problem(failed, 500, "INTERNAL_ERROR")
    assert after_failure == (untouched(1), (0, 0, 0))
    assert retried.status_code == 201, retried.text
    assert "idempotent-replayed" not in retried.headers
    assert await rows(db_engine, user_id) == Rows(1, 1, 0, 1, 0, 1)


# ------------------------------------------------------------- idempotency


async def test_the_same_key_with_another_payment_method_is_409_and_a_cash_replay_is_stored(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    phone, key = random_phone(), new_key()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        first = post(client, pickup_body(phone), key)
        replay = post(client, pickup_body(phone), key)
        conflict = post(
            client, checkout_body(fulfillment_method="pickup", contact_phone=phone), key
        )
    assert first.status_code == 201
    assert replay.status_code == 201 and replay.headers["idempotent-replayed"] == "true"
    assert replay.json() == first.json()
    assert_problem(conflict, 409, "IDEMPOTENCY_KEY_CONFLICT")
    assert (await rows(db_engine, user_id)).orders == 1


# -------------------------------------------------------------- address


async def test_a_deleted_foreign_or_unknown_address_is_the_same_422(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    other = await create_user(db_session)
    foreign = await seed_address(db_session, other.id)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        deleted = await seed_address(db_session, user_id, deleted_at=datetime.now(UTC))
        responses = [
            await refused_cash(client, db_engine, user_id, delivery_body(address))
            for address in (deleted, foreign, uuid.uuid4())
        ]
    for response in responses:
        assert_problem(response, 422, "INVALID_FULFILLMENT")
    assert len({r.json()["detail"] for r in responses}) == 1


async def test_delivery_with_a_contact_phone_and_pickup_without_an_address_are_refused(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        address = await seed_address(db_session, user_id)
        with_phone = await refused_cash(
            client, db_engine, user_id, delivery_body(address, contact_phone=random_phone())
        )
        async with setting(db_engine, "pickup_address", None):
            no_pickup = await refused_cash(client, db_engine, user_id, pickup_body(random_phone()))
        provider = await refused_cash(
            client, db_engine, user_id, pickup_body(random_phone(), payment_provider="mock")
        )
    assert_problem(with_phone, 422, "INVALID_FULFILLMENT")
    assert_problem(no_pickup, 422, "INVALID_FULFILLMENT")
    assert_problem(provider, 422, "PAYMENT_METHOD_NOT_ALLOWED")
    assert provider.json()["reason"] == "provider_not_applicable"


async def test_snapshots_survive_later_edits_to_the_address_and_the_product(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        phone = random_phone()
        address = await seed_address(db_session, user_id, phone)
        placed = post(client, delivery_body(address)).json()["order"]
    before = await order_row(db_engine, placed["id"])
    await db_session.execute(
        text(
            "UPDATE addresses SET city = 'Tripoli', street = 'Elsewhere', phone = '+96170111222'"
            " WHERE id = :a"
        ),
        {"a": address},
    )
    await db_session.execute(
        text("UPDATE addresses SET deleted_at = now() WHERE id = :a"), {"a": address}
    )
    await db_session.execute(
        text("UPDATE products SET production_lead_time_days = 30, batch_size = 1 WHERE id = :p"),
        {"p": lamp},
    )
    await db_session.commit()
    after = await order_row(db_engine, placed["id"])
    assert after == before
    assert (after.city, after.contact_phone_snapshot) == ("Beirut", phone)
    async with db_engine.connect() as conn:
        snapshot = (
            await conn.execute(
                text(
                    "SELECT lead_time_days_snapshot, batch_size_snapshot FROM order_items"
                    " WHERE order_id = :o"
                ),
                {"o": placed["id"]},
            )
        ).one()
    assert tuple(snapshot) == (3, 2)


# ------------------------------------------------------------------- Q13


async def test_a_mixed_cart_with_an_owned_stl_checks_out_cash_and_names_the_dropped_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    refs = await seed_refs(db_session)
    lamp, owned = await physical(db_session, refs), await stl(db_session, refs)
    key = new_key()
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp, owned)
        await seed_online_order(
            db_session, user_id=user_id, stl_id=owned, line_status="awaiting_delivery"
        )
        phone = random_phone()
        placed = post(client, pickup_body(phone), key)
        replay = post(client, pickup_body(phone), key)
    assert placed.status_code == 201, placed.text
    expected = [{"product_id": str(owned), "reason": "already_owned"}]
    assert placed.json()["dropped_lines"] == expected
    assert placed.json()["order"]["payment_method"] == "cash"
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["dropped_lines"] == expected
    assert (await rows(db_engine, user_id)).orders == 2  # the seeded STL order and this one


async def test_cash_without_the_cash_terms_is_a_validation_error_at_that_field(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    lamp = await physical(db_session)
    with client_for(main_app) as client:
        user_id = await signed_in_buyer(client, db_session, lamp)
        body = pickup_body(random_phone())
        del body["accept_cash_terms"]
        response = await refused_cash(client, db_engine, user_id, body)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert response.json()["errors"][0]["loc"] == ["body", "accept_cash_terms"]
