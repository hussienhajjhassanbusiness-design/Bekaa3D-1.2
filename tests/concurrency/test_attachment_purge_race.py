"""Two attachment purges at once (VS-034): SKIP LOCKED keeps them off each other's rows."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.integrations.storage.local import LocalStorage
from app.jobs.purge_expired_attachments import purge_expired_attachments
from tests.concurrency.barrier import SYNC_TIMEOUT_SECONDS, meet_or_fail
from tests.integration.engagement.custom_request_support import seed_request, surviving_keys

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]

EXPIRY = datetime(2000, 6, 1, tzinfo=UTC)


async def test_a_second_purge_skips_rows_the_first_holds_instead_of_waiting(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    """Without SKIP LOCKED the second purge blocks on the first, which waits for it: timeout."""
    storage = LocalStorage(tmp_path)
    _, keys = await seed_request(db_engine, storage, expires_at=EXPIRY, files=4)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    barrier, second_done = asyncio.Barrier(2), asyncio.Event()

    async def first() -> int:
        async with factory() as session, session.begin():
            repo = SqlCustomRequestRepository(session)
            held = await repo.lock_expired_attachments(now=EXPIRY, limit=100)
            await meet_or_fail(barrier)
            await asyncio.wait_for(second_done.wait(), timeout=SYNC_TIMEOUT_SECONDS)
            return await repo.delete_attachments([a.id for a in held])

    async def second() -> int:
        await meet_or_fail(barrier)
        async with factory() as session, session.begin():
            seen = await SqlCustomRequestRepository(session).lock_expired_attachments(
                now=EXPIRY, limit=100
            )
        second_done.set()
        return len([a for a in seen if a.storage_key in keys])

    deleted, overlap = await asyncio.wait_for(
        asyncio.gather(first(), second()), timeout=SYNC_TIMEOUT_SECONDS * 3
    )
    assert overlap == 0
    assert deleted >= len(keys)
    assert await surviving_keys(db_engine, keys) == set()


async def test_two_purge_jobs_split_the_work_without_error(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    keys: list[str] = []
    for _ in range(6):
        keys += (await seed_request(db_engine, storage, expires_at=EXPIRY, files=5))[1]
    ctx: dict[str, Any] = {"session_factory": async_sessionmaker(db_engine)}

    results = await asyncio.wait_for(
        asyncio.gather(
            purge_expired_attachments(ctx, now=EXPIRY, storage=storage, batch_size=4),
            purge_expired_attachments(ctx, now=EXPIRY, storage=storage, batch_size=4),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert sum(r["attachments"] for r in results if isinstance(r, dict)) >= len(keys)
    assert await surviving_keys(db_engine, keys) == set()
    assert await storage.list("custom-requests/") == []
