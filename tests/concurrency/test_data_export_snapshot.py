"""VS-044 (ADR-046): the export is one snapshot. Rows committed by another transaction after
its first read are absent from the body, though later data sets are read after the commit."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.reporting.infrastructure.export_adapters import SqlExportOrders
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import SYNC_TIMEOUT_SECONDS, meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, async_client, create_user, csrf, running_app
from tests.integration.reporting.export_support import EXPORT

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


async def test_rows_committed_after_the_first_read_are_not_exported(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await create_user(db_session)
    product = (await seed_product(db_session, await seed_refs(db_session))).id
    barrier, written = asyncio.Barrier(2), asyncio.Event()
    original = SqlExportOrders.page

    async def paused(self: SqlExportOrders, user_id: Any, **kwargs: Any) -> Any:
        if kwargs["after"] is None:  # the addresses were read: the snapshot is taken
            await meet_or_fail(barrier)
            await asyncio.wait_for(written.wait(), SYNC_TIMEOUT_SECONDS)
        return await original(self, user_id, **kwargs)

    async def writer() -> None:
        await meet_or_fail(barrier)
        async with db_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO reviews (user_id, product_id, rating) VALUES (:u, :p, 3)"),
                {"u": user.id, "p": product},
            )
            await conn.execute(
                text(
                    "INSERT INTO contact_messages (name, email, message, user_id)"
                    " VALUES ('Rana', 'rana@example.com', 'Late words', :u)"
                ),
                {"u": user.id},
            )
        written.set()

    monkeypatch.setattr(SqlExportOrders, "page", paused)
    async with running_app(make_app) as app, async_client(app) as client:
        login = await client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        headers = csrf(client)
        response, _ = await asyncio.gather(client.get(EXPORT, headers=headers), writer())
        assert response.status_code == 200, response.text
        during = response.json()
        monkeypatch.setattr(SqlExportOrders, "page", original)
        after = (await client.get(EXPORT, headers=headers)).json()
    assert (during["reviews"], during["contact_messages"]) == ([], [])
    assert (len(after["reviews"]), len(after["contact_messages"])) == (1, 1)
