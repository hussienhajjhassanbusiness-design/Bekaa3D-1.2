"""The purge while a refresh holds a session row (VS-046): no wait, live rows survive."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.identity.infrastructure.models import SessionModel
from app.identity.infrastructure.repositories import SessionRepository
from app.jobs.purge_security_records import purge_expired_security_records
from tests.integration.identity.test_purge_expired_security_records import (
    NOW,
    at,
    login_session,
    new_user,
    surviving,
)


@pytest.mark.concurrency
@pytest.mark.integration
async def test_a_locked_session_is_skipped_and_the_refresh_still_commits(
    db_engine: AsyncEngine,
) -> None:
    user = await new_user(db_engine)
    live = await login_session(db_engine, user, datetime.now(UTC) + timedelta(days=30), None)
    ended = await login_session(db_engine, user, at(1, 1), at(1, 1))
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    ctx = {"session_factory": factory}

    async with factory() as refresh, refresh.begin():
        repo = SessionRepository(refresh)
        locked_live = await repo.get_for_update(live)
        locked_ended = await repo.get_for_update(ended)
        assert locked_live is not None and locked_ended is not None

        await asyncio.wait_for(purge_expired_security_records(ctx, now=NOW), timeout=10)
        assert await surviving(db_engine, SessionModel, [ended]) == {ended}

        locked_live.last_used_at = datetime.now(UTC)
        await repo.save(locked_live)  # the refresh completes after the purge ran

    await purge_expired_security_records(ctx, now=NOW)
    assert await surviving(db_engine, SessionModel, [live, ended]) == {live}
