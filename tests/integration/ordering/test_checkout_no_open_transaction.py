"""No transaction is open while checkout waits on the provider (ADR-032; VS-023 plan
3.8). A slow fake provider holds the call; pg_stat_activity is read meanwhile."""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.ordering.checkout_support import (
    CHECKOUT,
    ITEMS,
    checkout_body,
    new_key,
    shop_open,  # noqa: F401
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "shop_open")]

OPEN_TRANSACTIONS = """
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = current_database() AND pid <> pg_backend_pid()
      AND state LIKE 'idle in transaction%'
"""


async def test_no_transaction_is_open_during_the_provider_call(
    db_engine: AsyncEngine, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    user = await create_user(db_session)
    await db_session.commit()  # `create_user` refreshes, which opens a transaction
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_create(request: Any) -> Any:
        entered.set()
        await release.wait()
        return await real_create(request)

    async with running_app(make_app) as app:
        provider = app.state.payment_providers["mock"]
        real_create = provider.create_payment
        provider.create_payment = slow_create
        client = async_client(app)
        try:
            await client.post(
                "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
            )
            csrf = {"X-CSRF-Token": client.cookies["csrf_token"]}
            await client.post(ITEMS, json={"product_id": str(stl)}, headers=csrf)
            request = asyncio.create_task(
                client.post(
                    CHECKOUT, json=checkout_body(), headers=csrf | {"Idempotency-Key": new_key()}
                )
            )
            await asyncio.wait_for(entered.wait(), timeout=10)
            async with db_engine.connect() as conn:
                open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
            release.set()
            response = await request
        finally:
            release.set()
            await client.aclose()
    assert response.status_code == 201, response.text
    assert open_during_call == 0
    assert uuid.UUID(response.json()["order"]["id"])
