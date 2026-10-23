"""VS-029 over HTTP: `/api/v1/admin/cash-blocks` list, search by phone and clear (SRS 9.8.6;
ADR-024 d6; ADR-038). Blocks are seeded directly, since VS-031 creates them."""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import hash_phone
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.ordering.checkout_support import (
    add_to_cart,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    pickup_body,
    post,
    random_phone,
    seed_block,
    setting,
    spaced,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

BLOCKS = "/api/v1/admin/cash-blocks"
SEARCH = f"{BLOCKS}/search"
CASH_NOT_AVAILABLE = "CASH_NOT_AVAILABLE"


@pytest_asyncio.fixture(autouse=True)
async def _pickup_address(db_engine: AsyncEngine) -> Any:
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        yield


def clear_path(block_id: uuid.UUID | str) -> str:
    return f"{BLOCKS}/{block_id}/clear"


async def _block(db: AsyncSession, user_id: uuid.UUID, phone: str, *, cleared: bool = False) -> str:
    await seed_block(db, user_id, phone)
    block_id = await db.scalar(
        text(
            "SELECT id FROM cash_payment_blocks WHERE user_id = :u AND contact_phone_hash = :h"
            " ORDER BY created_at DESC LIMIT 1"
        ),
        {"u": user_id, "h": hash_phone(phone)},
    )
    if cleared:
        admin = await create_user(db)
        await db.execute(
            text(
                "UPDATE cash_payment_blocks SET cleared_at = now(), cleared_by = :a WHERE id = :b"
            ),
            {"a": admin.id, "b": block_id},
        )
        await db.commit()
    return str(block_id)


def _search(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post(SEARCH, json=body, headers=csrf(client))


async def _audits(engine: AsyncEngine, block_id: str) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT actor_user_id, after_data FROM audit_logs"
                " WHERE action = 'cash_block.cleared' AND entity_id = :b"
            ),
            {"b": uuid.UUID(block_id)},
        )
        return list(rows.all())


async def test_a_customer_gets_404_and_anonymous_401_on_every_route(
    db_session: AsyncSession,
) -> None:
    buyer = await create_user(db_session)
    phone = random_phone()
    block_id = await _block(db_session, buyer.id, phone)
    with client_for(main_app) as client:
        anonymous = [
            client.get(BLOCKS).status_code,
            client.post(SEARCH, json={"phone": phone}).status_code,
            client.post(clear_path(block_id)).status_code,
        ]
        login(client, buyer.email, PASSWORD)
        customer = [
            client.get(BLOCKS, params={"customer_id": str(buyer.id)}),
            _search(client, {"phone": phone}),
            client.post(clear_path(block_id), headers=csrf(client)),
        ]
    assert anonymous == [401, 401, 401]
    for response in customer:
        assert_problem(response, 404, "NOT_FOUND")


async def test_the_list_filters_by_customer_and_by_active(db_session: AsyncSession) -> None:
    alice, bob = await create_user(db_session), await create_user(db_session)
    phone = random_phone()
    old = await _block(db_session, alice.id, random_phone(), cleared=True)
    active = await _block(db_session, alice.id, phone)
    await _block(db_session, bob.id, random_phone())
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        mine = client.get(BLOCKS, params={"customer_id": str(alice.id)})
        live = client.get(BLOCKS, params={"customer_id": str(alice.id), "active": "true"})
        gone = client.get(BLOCKS, params={"customer_id": str(alice.id), "active": "false"})
        paged = client.get(BLOCKS, params={"customer_id": str(alice.id), "limit": 1})
        next_page = client.get(
            BLOCKS,
            params={
                "customer_id": str(alice.id),
                "limit": 1,
                "cursor": paged.json()["next_cursor"],
            },
        )
    assert [b["id"] for b in mine.json()["items"]] == [active, old]
    assert [b["id"] for b in live.json()["items"]] == [active]
    assert [b["id"] for b in gone.json()["items"]] == [old]
    assert [b["id"] for b in paged.json()["items"] + next_page.json()["items"]] == [active, old]
    first = mine.json()["items"][0]
    assert (first["customer_id"], first["reason"], first["active"]) == (
        str(alice.id),
        "refused",
        True,
    )
    assert first["order_number"].startswith("B3D-")
    assert phone not in mine.text and hash_phone(phone) not in mine.text


async def test_search_matches_any_spelling_of_the_phone(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    phone = random_phone()
    block_id = await _block(db_session, buyer.id, phone)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        e164 = _search(client, {"phone": phone})
        typed = _search(client, {"phone": spaced(phone)})
        local = _search(client, {"phone": "0" + phone[4:]})
        other = _search(client, {"phone": random_phone()})
        inactive = _search(client, {"phone": phone, "active": False})
    for response in (e164, typed, local):
        assert response.status_code == 200, response.text
        assert [b["id"] for b in response.json()["items"]] == [block_id]
    assert other.json()["items"] == [] and inactive.json()["items"] == []
    assert phone not in e164.text


@pytest.mark.parametrize(
    "body",
    [
        {"phone": "12"},
        {"phone": "+33612345678"},
        {"phone": "+96171123456", "user_id": str(uuid.uuid4())},
        {},
    ],
)
async def test_a_bad_search_is_a_validation_error(
    body: dict[str, Any], db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _search(client, body)
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_search_and_clear_need_csrf(db_session: AsyncSession) -> None:
    buyer = await create_user(db_session)
    phone = random_phone()
    block_id = await _block(db_session, buyer.id, phone)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        search = client.post(SEARCH, json={"phone": phone})
        clear = client.post(clear_path(block_id))
        after = client.get(BLOCKS, params={"customer_id": str(buyer.id), "active": "true"})
    assert_problem(search, 403, "CSRF_INVALID")
    assert_problem(clear, 403, "CSRF_INVALID")
    assert [b["id"] for b in after.json()["items"]] == [block_id]


async def test_clearing_is_audited_and_a_second_clear_changes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    buyer = await create_user(db_session)
    block_id = await _block(db_session, buyer.id, random_phone())
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        first = client.post(clear_path(block_id), headers=csrf(client))
        second = client.post(clear_path(block_id), headers=csrf(client))
        unknown = client.post(clear_path(uuid.uuid4()), headers=csrf(client))
    assert first.status_code == 200 and second.status_code == 200, first.text
    assert first.json()["active"] is False
    assert first.json()["cleared_by"] == str(admin.id)
    assert second.json() == first.json()
    assert_problem(unknown, 404, "NOT_FOUND")
    [audit] = await _audits(db_engine, block_id)
    assert audit.actor_user_id == admin.id
    assert audit.after_data["customer_id"] == str(buyer.id)
    assert audit.after_data["reason"] == "refused"
    assert not any("phone" in key for key in audit.after_data)


async def test_after_clearing_checkout_offers_cash_again_by_account_and_phone(
    db_session: AsyncSession,
) -> None:
    buyer, other = await create_user(db_session), await create_user(db_session)
    phone = random_phone()
    block_id = await _block(db_session, buyer.id, phone)
    lamp = await physical(db_session)
    refused = {}
    for user in (buyer, other):
        with client_for(main_app) as client:
            login(client, user.email, PASSWORD)
            add_to_cart(client, lamp)
            refused[user.id] = post(client, pickup_body(phone))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert client.post(clear_path(block_id), headers=csrf(client)).status_code == 200
    placed = {}
    for user in (buyer, other):
        with client_for(main_app) as client:
            login(client, user.email, PASSWORD)
            placed[user.id] = post(client, pickup_body(spaced(phone)))
            if user is buyer:  # one open cash order per phone: let the other account in
                order_id = placed[user.id].json()["order"]["id"]
                await db_session.execute(
                    text("UPDATE orders SET status = 'completed' WHERE id = :o"), {"o": order_id}
                )
                await db_session.commit()
    for response in refused.values():
        assert_problem(response, 422, CASH_NOT_AVAILABLE)
    for response in placed.values():
        assert response.status_code == 201, response.text
