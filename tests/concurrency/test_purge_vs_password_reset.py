"""The purge against a password reset in flight (VS-046, ADR-018 lock order).

The reset holds `users`, then updates the user's expired-but-unrevoked sessions, the very
rows the purge targets. SKIP LOCKED means the purge neither waits nor deadlocks."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.identity.infrastructure.models import SessionModel
from app.identity.infrastructure.repositories import SessionRepository, UserRepository
from app.jobs.purge_security_records import purge_expired_security_records
from tests.integration.identity.test_purge_expired_security_records import (
    NOW,
    at,
    login_session,
    new_user,
    surviving,
)

TIMEOUT_SECONDS = 10


@pytest.mark.concurrency
@pytest.mark.integration
async def test_the_purge_skips_rows_a_reset_holds_and_takes_them_next_time(
    db_engine: AsyncEngine,
) -> None:
    user = await new_user(db_engine)
    held = [await login_session(db_engine, user, at(1, 1), None) for _ in range(3)]
    other_user = await new_user(db_engine)
    free = await login_session(db_engine, other_user, at(1, 1), None)
    ctx = {"session_factory": async_sessionmaker(db_engine, expire_on_commit=False)}

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as reset, reset.begin():
        # What ConfirmPasswordReset does: user row first, then that user's sessions.
        assert await UserRepository(reset).get_by_id_for_update(user) is not None
        await SessionRepository(reset).revoke_all_for_user(user_id=user, at=datetime.now(UTC))

        await asyncio.wait_for(
            purge_expired_security_records(ctx, now=NOW), timeout=TIMEOUT_SECONDS
        )
        assert await surviving(db_engine, SessionModel, held) == set(held)
        assert await surviving(db_engine, SessionModel, [free]) == set()

    await asyncio.wait_for(purge_expired_security_records(ctx, now=NOW), timeout=TIMEOUT_SECONDS)
    assert await surviving(db_engine, SessionModel, held) == set()


@pytest.mark.concurrency
@pytest.mark.integration
async def test_a_reset_and_a_purge_started_together_both_finish(db_engine: AsyncEngine) -> None:
    """Either order of lock acquisition completes: the purge never waits, so no cycle forms."""
    user = await new_user(db_engine)
    rows = [await login_session(db_engine, user, at(1, 1), None) for _ in range(20)]
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def reset() -> int:
        async with factory() as s, s.begin():
            await UserRepository(s).get_by_id_for_update(user)
            return await SessionRepository(s).revoke_all_for_user(
                user_id=user, at=datetime.now(UTC)
            )

    for _ in range(5):
        results = await asyncio.wait_for(
            asyncio.gather(
                reset(),
                purge_expired_security_records({"session_factory": factory}, now=NOW),
                return_exceptions=True,
            ),
            timeout=TIMEOUT_SECONDS,
        )
        assert not [r for r in results if isinstance(r, BaseException)], results
    await purge_expired_security_records({"session_factory": factory}, now=NOW)
    assert await surviving(db_engine, SessionModel, rows) == set()
