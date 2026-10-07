import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.refresh_session import RefreshResult, RefreshSession
from app.identity.application.security.session_tokens import issue_refresh_token
from app.identity.application.security.token_service import hash_token
from app.identity.domain.exceptions import RefreshTokenReuseError, SessionTerminatedError
from app.identity.infrastructure.repositories import SessionRepository, UserRepository
from app.platform.public import SqlAuditWriter as AuditWriter


async def _seed_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    now = datetime.now(UTC)
    session_id = uuid.uuid4()
    expires_at = now + timedelta(days=30)
    raw_token = issue_refresh_token(
        session_id=session_id, token_version=1, expires_at=expires_at, now=now
    )

    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com", password_hash="not-a-real-hash"
        )
        await SessionRepository(db).add(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_token(raw_token),
            expires_at=expires_at,
            ip_hash=None,
            user_agent=None,
        )
    return session_id, raw_token


async def _refresh_once(
    session_factory: async_sessionmaker[AsyncSession], raw_token: str
) -> RefreshResult:
    """One request's worth of work, transaction boundary included - mirroring
    what get_session + the refresh route do, so the commit-despite-failure
    behaviour is exercised rather than assumed."""
    async with session_factory() as db, db.begin():
        use_case = RefreshSession(
            user_repo=UserRepository(db),
            session_repo=SessionRepository(db),
            audit_writer=AuditWriter(db),
        )
        try:
            return await use_case.execute(
                raw_refresh_token=raw_token, request_id=None, ip_hash=None
            )
        except SessionTerminatedError:
            await db.commit()
            raise


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_simultaneous_refreshes_of_one_token_produce_exactly_one_winner(
    db_engine: AsyncEngine,
) -> None:
    """FR-02: "when the same refresh token is submitted concurrently, at most
    one rotation succeeds".

    Without SELECT ... FOR UPDATE in SessionRepository.get_for_update, both
    transactions would read token_version 1, both would validate, and both
    would rotate - which would also mean a genuinely stolen token could be
    rotated alongside the real one without ever being noticed."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    session_id, raw_token = await _seed_session(session_factory)

    outcomes = await asyncio.gather(
        _refresh_once(session_factory, raw_token),
        _refresh_once(session_factory, raw_token),
        return_exceptions=True,
    )

    successes = [o for o in outcomes if isinstance(o, RefreshResult)]
    reuse_errors = [o for o in outcomes if isinstance(o, RefreshTokenReuseError)]
    assert len(successes) == 1, outcomes
    assert len(reuse_errors) == 1, outcomes

    async with session_factory() as db:
        row = await SessionRepository(db).get_for_update(session_id)

    assert row is not None
    # Exactly one rotation happened - not two.
    assert row.token_version == 2
    # ...and the loser was treated as a replay, which kills the session.
    assert row.reuse_detected_at is not None
    assert row.revoked_at is not None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_concurrent_refreshes_of_separate_sessions_both_succeed(
    db_engine: AsyncEngine,
) -> None:
    """The lock must be per-session. If it serialised all refreshes, unrelated
    users would block each other under load."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    _, first_token = await _seed_session(session_factory)
    _, second_token = await _seed_session(session_factory)

    outcomes = await asyncio.gather(
        _refresh_once(session_factory, first_token),
        _refresh_once(session_factory, second_token),
        return_exceptions=True,
    )

    assert all(isinstance(o, RefreshResult) for o in outcomes), outcomes
