"""I20 (VS-030 plan 2.6, Q8): each cash-block search writes one `cash_block.searched` audit
row with the filters, the count and the block ids, never the phone or its hash."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.phone import normalise_lebanese_phone
from app.core.security import hash_phone
from app.main import app as main_app
from tests.integration.deep_support import client_for, create_user, csrf, mfa_admin
from tests.integration.ordering.physical_support import random_phone, seed_block, spaced

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

SEARCH = "/api/v1/admin/cash-blocks/search"


async def test_a_search_is_audited_without_the_phone_or_its_hash(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    phone = random_phone()
    buyer = (await create_user(db_session)).id
    await seed_block(db_session, buyer, phone)
    with client_for(main_app) as client:
        admin = (await mfa_admin(client, db_session))[0].id
        response = client.post(
            SEARCH, json={"phone": spaced(phone), "limit": 5}, headers=csrf(client)
        )
    assert response.status_code == 200, response.text
    block_ids = [item["id"] for item in response.json()["items"]]
    assert len(block_ids) == 1
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, entity_type, entity_id, before_data, after_data"
                    " FROM audit_logs WHERE action = 'cash_block.searched'"
                    " AND after_data->'block_ids' ? :b"
                ),
                {"b": block_ids[0]},
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == admin and row.entity_type == "cash_block"
    assert row.after_data == {
        "active": None,
        "limit": 5,
        "result_count": 1,
        "block_ids": block_ids,
    }
    stored = json.dumps([row.before_data, row.after_data])
    for secret in (phone, normalise_lebanese_phone(phone), spaced(phone), hash_phone(phone)):
        assert secret not in stored
