"""Two purges at once (VS-046): disjoint rows via SKIP LOCKED, no errors, nothing left."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.identity.infrastructure.models import SessionModel
from app.jobs.purge_security_records import purge_expired_security_records
from tests.integration.identity.test_purge_expired_security_records import (
    NOW,
    at,
    login_session,
    new_user,
    surviving,
)

BATCH = 25


@pytest.mark.concurrency
@pytest.mark.integration
async def test_two_purges_split_the_work_without_error(db_engine: AsyncEngine) -> None:
    user = await new_user(db_engine)
    rows = [await login_session(db_engine, user, at(1, 1), None) for _ in range(3 * BATCH)]
    ctx = {"session_factory": async_sessionmaker(db_engine, expire_on_commit=False)}

    results = await asyncio.wait_for(
        asyncio.gather(
            purge_expired_security_records(ctx, now=NOW, batch_size=BATCH),
            purge_expired_security_records(ctx, now=NOW, batch_size=BATCH),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert not [r for r in results if isinstance(r, BaseException)], results
    counted = [r for r in results if isinstance(r, dict)]
    assert sum(r["sessions"] for r in counted) >= len(rows)  # >=: other 2000-era rows may exist
    assert await surviving(db_engine, SessionModel, rows) == set()
