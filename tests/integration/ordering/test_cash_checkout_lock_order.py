"""The SQL each checkout path sends, in order (VS-028 plan 8.1): claim, cart, address
FOR SHARE, the phone advisory lock, then reads and INSERTs. No existing `orders` row is locked."""

import re

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for
from tests.integration.ordering.checkout_support import checkout_body, shop_open  # noqa: F401
from tests.integration.ordering.physical_support import (
    delivery_body,
    physical,
    pickup_body,
    post,
    random_phone,
    seed_address,
    setting,
    signed_in_buyer,
)
from tests.integration.ordering.test_lock_order import captured

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

_LOCK = re.compile(r"FOR UPDATE|FOR SHARE|ON CONFLICT|pg_advisory", re.IGNORECASE)
_TABLE = re.compile(r"(?:\bFROM|\bINTO|^UPDATE)\s+(\w+)")


def lock_steps(statements: list[str]) -> list[str]:
    steps = []
    for s in statements:
        if "pg_advisory_xact_lock" in s:
            steps.append("advisory")
        elif _LOCK.search(s):
            steps.append(f"{_TABLE.findall(s)[0]}:{'share' if 'FOR SHARE' in s else 'lock'}")
    return steps


@pytest.mark.parametrize("method", ["delivery", "pickup", "online-delivery"])
async def test_each_physical_path_takes_its_locks_in_the_plan_order(
    db_engine: AsyncEngine, db_session: AsyncSession, method: str
) -> None:
    lamp = await physical(db_session)
    async with setting(db_engine, "pickup_address", "Workshop"):
        with client_for(main_app) as client:
            user_id = await signed_in_buyer(client, db_session, lamp)
            address = await seed_address(db_session, user_id)
            body = {
                "delivery": delivery_body(address),
                "pickup": pickup_body(random_phone()),
                "online-delivery": checkout_body(
                    fulfillment_method="delivery", address_id=str(address)
                ),
            }[method]
            with captured(main_app.state.db_engine.sync_engine) as statements:
                response = post(client, body)
    assert response.status_code == 201, response.text
    steps = lock_steps(statements)
    print(f"\n{method}:", *steps, sep="\n  ")
    expected = {
        "delivery": ["idempotency_records:lock", "carts:lock", "addresses:share", "advisory"],
        "pickup": ["idempotency_records:lock", "carts:lock", "advisory"],
        "online-delivery": ["idempotency_records:lock", "carts:lock", "addresses:share"],
    }[method]
    assert steps == expected
    first_insert = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO orders"))
    last_lock = max(i for i, s in enumerate(statements) if _LOCK.search(s))
    assert last_lock < first_insert
    assert not any(re.search(r"FROM orders\b.*FOR UPDATE", s) for s in statements)
