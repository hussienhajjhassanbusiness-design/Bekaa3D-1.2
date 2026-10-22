"""The contact phone and its keyed hash never leave the order row (VS-028 plan 6.5, Revision 1
item 2). One sentinel number goes through every checkout path and refusal; none of its spellings
or its hash may appear in a response, a log line, an audit row, an outbox payload, a
notification or a stored idempotency response. Only the owner's order detail may show it."""

import io
import json
import logging
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import app.ordering.api.checkout as checkout_api
from app.core.config import get_settings
from app.core.security import hash_phone
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, login
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    checkout_body,
    new_key,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    cash_body,
    delivery_body,
    physical,
    pickup_body,
    post,
    seed_address,
    seed_block,
    seed_cash_order,
    setting,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open"),
]

SENTINEL = "+96171999888"
SPELLINGS = ("71 999 888", "+961 71 999 888")
INVALID = "+961 71 999 888 77"


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Every handler the app configures writes into this buffer, through its formatter."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    return buffer


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


def needles() -> dict[str, str]:
    return {
        "e164": SENTINEL,
        "national digits": "71999888",
        "digits with country code": "96171999888",
        "phone hash": hash_phone(SENTINEL),
        "salt": get_settings().phone_hash_salt.get_secret_value(),
        "spelling as sent": SPELLINGS[0],
        "international spelling as sent": SPELLINGS[1],
        "invalid input as sent": INVALID,
    }


def scan(haystack: str, where: str) -> None:
    for name, needle in needles().items():
        assert needle not in haystack, f"{name} leaked into {where}"


def scan_response(response: httpx.Response, where: str) -> None:
    scan(response.text + json.dumps(dict(response.headers)), where)


async def clear_sentinel_state(db: AsyncSession) -> None:
    """Free the limit and drop the blocks between cases, so each refusal is reached."""
    digest = hash_phone(SENTINEL)
    await db.execute(
        text(
            "UPDATE order_items SET fulfillment_status = 'cancelled', cancelled_at = now()"
            " WHERE order_id IN (SELECT id FROM orders WHERE contact_phone_hash = :h"
            " AND payment_method = 'cash')"
        ),
        {"h": digest},
    )
    await db.execute(
        text(
            "UPDATE orders SET status = 'cancelled' WHERE contact_phone_hash = :h"
            " AND payment_method = 'cash'"
        ),
        {"h": digest},
    )
    await db.execute(
        text("DELETE FROM cash_payment_blocks WHERE contact_phone_hash = :h"), {"h": digest}
    )
    await db.commit()


async def shopper(db: AsyncSession, client: Any, price_cents: int = 1000) -> Any:
    user = await create_user(db)
    login(client, user.email)
    add_to_cart(client, await physical(db, price_cents=price_cents))
    return user


async def test_the_sentinel_phone_and_its_hash_reach_no_response_log_or_stored_row(
    db_engine: AsyncEngine, db_session: AsyncSession, app_logs: io.StringIO
) -> None:
    responses: list[tuple[str, httpx.Response]] = []

    def record(label: str, response: httpx.Response) -> httpx.Response:
        responses.append((label, response))
        return response

    detail_text = ""
    with client_for(main_app, raise_server_exceptions=False) as client:
        owner = await shopper(db_session, client)
        address = await seed_address(db_session, owner.id, SENTINEL)
        online_delivery = record(
            "online delivery",
            post(client, checkout_body(fulfillment_method="delivery", address_id=str(address))),
        )
        add_to_cart(client, await physical(db_session))
        online_pickup = record(
            "online pickup",
            post(
                client,
                checkout_body(fulfillment_method="pickup", contact_phone=SPELLINGS[0]),
            ),
        )
        add_to_cart(client, await physical(db_session))
        key = new_key()
        cash = record("cash pickup", post(client, pickup_body(SPELLINGS[1]), key))
        record("replay", post(client, pickup_body(SPELLINGS[1]), key))
        record(
            "conflict",
            post(client, cash_body(fulfillment_method="delivery", address_id=str(address)), key),
        )
        add_to_cart(client, await physical(db_session))
        record("same account open_orders", post(client, pickup_body(SPELLINGS[0])))
        for response in (online_delivery, online_pickup, cash):
            assert response.status_code == 201, response.text
        order_id = cash.json()["order"]["id"]
        detail = client.get(f"/api/v1/me/orders/{order_id}")
        listing = client.get("/api/v1/me/orders")
        detail_text = detail.text
        record("order list", listing)

    # Case matrix with fresh accounts: each refusal reached with the sentinel phone.
    other = await create_user(db_session)
    async with setting(db_engine, "cash_max_order_total", {"amount_cents": 1, "currency": "USD"}):
        await clear_sentinel_state(db_session)
        with client_for(main_app, raise_server_exceptions=False) as client:
            await shopper(db_session, client)
            record("order_total", post(client, pickup_body(SPELLINGS[0])))
    async with setting(db_engine, "cash_payment_enabled", False):
        with client_for(main_app, raise_server_exceptions=False) as client:
            await shopper(db_session, client)
            record("cash_disabled", post(client, pickup_body(SPELLINGS[0])))
    with client_for(main_app, raise_server_exceptions=False) as client:
        await shopper(db_session, client, price_cents=0)
        record("zero_total", post(client, pickup_body(SPELLINGS[0])))
    with client_for(main_app, raise_server_exceptions=False) as client:
        await shopper(db_session, client)
        record("invalid phone", post(client, pickup_body(INVALID)))
    await seed_cash_order(db_session, other.id, SENTINEL)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await shopper(db_session, client)
        record("open_orders by phone", post(client, pickup_body(SPELLINGS[0])))
    await clear_sentinel_state(db_session)
    await seed_block(db_session, other.id, SENTINEL)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await shopper(db_session, client)
        record("blocked by phone", post(client, pickup_body(SPELLINGS[1])))
    await clear_sentinel_state(db_session)
    blocked = await create_user(db_session)
    await seed_block(db_session, blocked.id, "+96170123456")
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, blocked.email)
        add_to_cart(client, await physical(db_session))
        record("blocked by account", post(client, pickup_body(SPELLINGS[0])))
    await clear_sentinel_state(db_session)

    # A forced CHECK violation: the database error text can carry the failing row.

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(checkout_api, "hash_phone", lambda _phone: "not-a-hash")
        with client_for(main_app, raise_server_exceptions=False) as client:
            await shopper(db_session, client)
            forced = record(
                "forced ck_orders_phone_hash_format", post(client, pickup_body(SENTINEL))
            )
    assert forced.status_code == 500

    codes = {label: r.status_code for label, r in responses}
    assert codes["order_total"] == codes["cash_disabled"] == codes["zero_total"] == 422
    assert codes["invalid phone"] == codes["open_orders by phone"] == 422
    assert codes["blocked by phone"] == codes["blocked by account"] == 422

    for label, response in responses:
        scan_response(response, f"the {label} response")

    logs = app_logs.getvalue()
    assert "checkout" in logs or "POST" in logs, "no events were captured: the scan is vacuous"
    scan(logs, "the logs")

    async with db_engine.connect() as conn:
        for table, column in (
            ("audit_logs", "coalesce(before_data::text, '') || coalesce(after_data::text, '')"),
            ("email_outbox", "payload::text"),
            ("notifications", "payload::text"),
            ("idempotency_records", "coalesce(response_body::text, '')"),
        ):
            rows: list[str] = list(
                (await conn.execute(text(f"SELECT {column} FROM {table}"))).scalars()
            )
            scan(" ".join(rows), table)
        placed = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action = 'order.placed'")
        )
        outbox = await conn.scalar(
            text("SELECT count(*) FROM email_outbox WHERE template = 'order_cash_placed'")
        )
        blocks = await conn.scalar(text("SELECT count(*) FROM cash_payment_blocks"))
    assert placed and outbox, "the stores the scan reads were empty"
    assert blocks is not None

    # The one allowlisted route: the owner's order detail shows the E.164 form and nothing else.
    body = json.loads(detail_text)
    assert body["contact_phone"] == SENTINEL
    rest = json.dumps({k: v for k, v in body.items() if k != "contact_phone"})
    scan(rest, "the rest of the order detail")


async def test_a_cash_order_notice_carries_no_phone_and_no_address(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        user = await shopper(db_session, client)
        address = await seed_address(db_session, user.id, SENTINEL, street="Hamra St 77")
        response = post(client, delivery_body(address))
        await db_session.commit()
    assert response.status_code == 201, response.text
    async with db_engine.connect() as conn:
        payload = await conn.scalar(
            text(
                "SELECT payload::text FROM email_outbox WHERE template = 'order_cash_placed'"
                " AND user_id = :u"
            ),
            {"u": user.id},
        )
    assert payload is not None
    for fragment in ("Hamra", "Rita", "Beirut", "Blue door"):
        assert fragment not in payload
    scan(payload, "the cash order email payload")
    assert json.loads(payload)["delivery_fee_note"]
