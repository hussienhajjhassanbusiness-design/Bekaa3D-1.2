"""VS-034 / SRS 13.4, BR-115: `purge_expired_attachments` removes file and row at expiry,
keeps the lead itself, and is idempotent."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.integrations.storage.local import LocalStorage
from app.jobs.purge_expired_attachments import purge_expired_attachments
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from tests.integration.engagement.custom_request_support import (
    request_exists,
    seed_request,
    surviving_keys,
)

pytestmark = pytest.mark.integration

# Far in the past, so rows other tests create (expiring in the future) are never in scope.
EXPIRY = datetime(2001, 3, 4, 5, 6, 7, tzinfo=UTC)
# Later than EXPIRY, so the row the -1 s case leaves never enters another test's batch.
BOUNDARY = EXPIRY + timedelta(days=1)


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


@pytest.mark.parametrize(
    ("offset", "purged"),
    [(timedelta(seconds=-1), False), (timedelta(0), True), (timedelta(seconds=1), True)],
    ids=["expiry-minus-1s", "exactly-at-expiry", "expiry-plus-1s"],
)
async def test_an_attachment_is_purged_from_the_instant_it_expires(
    db_engine: AsyncEngine, tmp_path: Path, offset: timedelta, purged: bool
) -> None:
    storage = LocalStorage(tmp_path)
    _, keys = await seed_request(db_engine, storage, expires_at=BOUNDARY)
    await purge_expired_attachments(_ctx(db_engine), now=BOUNDARY + offset, storage=storage)
    assert (await surviving_keys(db_engine, keys) == set()) is purged
    assert [await storage.exists(key) for key in keys] == [not purged] * len(keys)


async def test_the_purge_deletes_file_and_row_but_keeps_the_lead(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    request_id, keys = await seed_request(db_engine, storage, expires_at=EXPIRY, files=3)
    await purge_expired_attachments(_ctx(db_engine), now=EXPIRY, storage=storage)
    assert await surviving_keys(db_engine, keys) == set()
    assert await storage.list("") == []
    assert await request_exists(db_engine, request_id)


async def test_a_second_run_is_a_no_op(db_engine: AsyncEngine, tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    await seed_request(db_engine, storage, expires_at=EXPIRY)
    first = await purge_expired_attachments(_ctx(db_engine), now=EXPIRY, storage=storage)
    second = await purge_expired_attachments(_ctx(db_engine), now=EXPIRY, storage=storage)
    assert first["attachments"] >= 2
    assert second == {"attachments": 0, "truncated": 0}


async def test_a_missing_file_still_purges_the_row(db_engine: AsyncEngine, tmp_path: Path) -> None:
    """The state a crash between file delete and commit leaves; the next run finishes it."""
    storage = LocalStorage(tmp_path)
    _, keys = await seed_request(db_engine, storage, expires_at=EXPIRY, write_files=False)
    await purge_expired_attachments(_ctx(db_engine), now=EXPIRY, storage=storage)
    assert await surviving_keys(db_engine, keys) == set()


async def test_a_capped_run_reports_truncated_and_the_next_run_finishes(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    _, keys = await seed_request(db_engine, storage, expires_at=EXPIRY, files=5)
    ctx = _ctx(db_engine)
    capped = await purge_expired_attachments(
        ctx, now=EXPIRY, storage=storage, batch_size=2, max_batches=1
    )
    assert capped == {"attachments": 2, "truncated": 1}
    assert len(await surviving_keys(db_engine, keys)) == 3
    await purge_expired_attachments(ctx, now=EXPIRY, storage=storage)
    assert await surviving_keys(db_engine, keys) == set()


async def test_an_unexpired_attachment_is_kept_with_its_file(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    later = datetime.now(UTC) + timedelta(days=30)
    _, keys = await seed_request(db_engine, storage, expires_at=later)
    await purge_expired_attachments(_ctx(db_engine), storage=storage)
    assert await surviving_keys(db_engine, keys) == set(keys)
    assert [await storage.exists(key) for key in keys] == [True] * len(keys)


def test_the_job_is_registered_daily() -> None:
    assert purge_expired_attachments in FUNCTIONS
    [job] = [j for j in CRON_JOBS if j.coroutine is purge_expired_attachments]
    assert (job.hour, job.minute, job.second) == (3, 35, 0)
