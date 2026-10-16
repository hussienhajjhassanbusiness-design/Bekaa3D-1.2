"""`purge_expired_security_records` against PostgreSQL (VS-046, amendment A).

`now` is pinned in the year 2000, so only rows dated in that era can match;
every assertion is by row id. Defaults: tokens 7 d, sessions 30 d past their end."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.identity.infrastructure.models import (
    PasswordResetTokenModel,
    SessionModel,
    VerificationTokenModel,
)
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
    VerificationTokenRepository,
)
from app.jobs.purge_security_records import purge_expired_security_records
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from app.platform.domain.exceptions import InvalidSettingValueError

NOW = datetime(2000, 3, 1, tzinfo=UTC)
TOKEN_CUTOFF = NOW - timedelta(days=7)  # 2000-02-23
SESSION_CUTOFF = NOW - timedelta(days=30)  # 2000-01-31


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def new_user(engine: AsyncEngine) -> uuid.UUID:
    async with async_sessionmaker(engine)() as s, s.begin():
        user = await UserRepository(s).add(
            email=f"purge046-{uuid.uuid4().hex}@example.com", password_hash="x"
        )
    return user.id


async def verification_token(
    engine: AsyncEngine, user_id: uuid.UUID, expires_at: datetime, *, used: bool = False
) -> uuid.UUID:
    async with async_sessionmaker(engine)() as s, s.begin():
        token = await VerificationTokenRepository(s).add(
            user_id=user_id, token_hash=uuid.uuid4().hex * 2, expires_at=expires_at
        )
        if used:
            await s.execute(
                update(VerificationTokenModel)
                .where(VerificationTokenModel.id == token.id)
                .values(used_at=expires_at - timedelta(hours=1))
            )
    return token.id


async def reset_token(
    engine: AsyncEngine, user_id: uuid.UUID, expires_at: datetime, *, used: bool = False
) -> uuid.UUID:
    async with async_sessionmaker(engine)() as s, s.begin():
        token = await PasswordResetTokenRepository(s).add(
            user_id=user_id, token_hash=uuid.uuid4().hex * 2, expires_at=expires_at
        )
        if used:
            await s.execute(
                update(PasswordResetTokenModel)
                .where(PasswordResetTokenModel.id == token.id)
                .values(used_at=expires_at - timedelta(minutes=10))
            )
    return token.id


async def login_session(
    engine: AsyncEngine, user_id: uuid.UUID, expires_at: datetime, revoked_at: datetime | None
) -> uuid.UUID:
    session_id = uuid.uuid4()
    async with async_sessionmaker(engine)() as s, s.begin():
        await SessionRepository(s).add(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=uuid.uuid4().hex * 2,
            expires_at=expires_at,
            ip_hash=None,
            user_agent=None,
        )
        if revoked_at is not None:
            await s.execute(
                update(SessionModel)
                .where(SessionModel.id == session_id)
                .values(revoked_at=revoked_at)
            )
    return session_id


async def surviving(engine: AsyncEngine, model: Any, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    async with async_sessionmaker(engine)() as s:
        return set((await s.scalars(select(model.id).where(model.id.in_(ids)))).all())


def at(month: int, day: int) -> datetime:
    return datetime(2000, month, day, tzinfo=UTC)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("model", "make"),
    [(VerificationTokenModel, verification_token), (PasswordResetTokenModel, reset_token)],
    ids=["verification", "password-reset"],
)
async def test_tokens_go_only_once_past_expiry_plus_retention(
    db_engine: AsyncEngine, model: Any, make: Any
) -> None:
    user = await new_user(db_engine)
    live = await make(db_engine, user, NOW + timedelta(hours=1))
    within = await make(db_engine, user, TOKEN_CUTOFF + timedelta(hours=1))
    past = await make(db_engine, user, TOKEN_CUTOFF - timedelta(hours=1))
    used_past = await make(db_engine, user, TOKEN_CUTOFF - timedelta(days=3), used=True)
    used_within = await make(db_engine, user, TOKEN_CUTOFF + timedelta(days=1), used=True)

    result = await purge_expired_security_records(_ctx(db_engine), now=NOW)

    ids = [live, within, past, used_past, used_within]
    assert await surviving(db_engine, model, ids) == {live, within, used_within}
    assert result["truncated"] == 0


@pytest.mark.integration
async def test_sessions_go_once_their_end_is_past_retention(db_engine: AsyncEngine) -> None:
    """The end is the earlier of expires_at and revoked_at (amendment A)."""
    user = await new_user(db_engine)
    live = await login_session(db_engine, user, at(3, 31), None)
    revoked_within = await login_session(db_engine, user, at(3, 31), at(2, 15))
    revoked_past = await login_session(db_engine, user, at(3, 31), at(1, 15))
    expired_past = await login_session(db_engine, user, at(1, 10), None)
    expired_within_revoked_long_ago = await login_session(db_engine, user, at(2, 20), at(1, 5))
    expired_and_revoked_within = await login_session(db_engine, user, at(2, 20), at(2, 19))
    expired_exactly_at_cutoff = await login_session(db_engine, user, SESSION_CUTOFF, None)

    await purge_expired_security_records(_ctx(db_engine), now=NOW)

    ids = [
        live,
        revoked_within,
        revoked_past,
        expired_past,
        expired_within_revoked_long_ago,
        expired_and_revoked_within,
        expired_exactly_at_cutoff,
    ]
    assert await surviving(db_engine, SessionModel, ids) == {
        live,
        revoked_within,
        expired_and_revoked_within,
        expired_exactly_at_cutoff,  # strictly older than the cutoff goes
    }


@pytest.mark.integration
async def test_present_day_rows_are_never_touched(db_engine: AsyncEngine) -> None:
    user = await new_user(db_engine)
    real_now = datetime.now(UTC)
    token = await verification_token(db_engine, user, real_now - timedelta(days=400))
    session = await login_session(db_engine, user, real_now - timedelta(days=400), None)
    await purge_expired_security_records(_ctx(db_engine), now=NOW)
    assert await surviving(db_engine, VerificationTokenModel, [token]) == {token}
    assert await surviving(db_engine, SessionModel, [session]) == {session}


@pytest.mark.integration
async def test_a_rerun_deletes_nothing_more_of_ours(db_engine: AsyncEngine) -> None:
    user = await new_user(db_engine)
    keep = await login_session(db_engine, user, at(3, 31), at(2, 15))
    gone = await login_session(db_engine, user, at(1, 1), None)
    await purge_expired_security_records(_ctx(db_engine), now=NOW)
    assert await surviving(db_engine, SessionModel, [keep, gone]) == {keep}
    await purge_expired_security_records(_ctx(db_engine), now=NOW)
    assert await surviving(db_engine, SessionModel, [keep, gone]) == {keep}


@pytest.mark.integration
async def test_a_capped_run_reports_truncated_and_the_next_run_finishes(
    db_engine: AsyncEngine,
) -> None:
    user = await new_user(db_engine)
    ids = [await reset_token(db_engine, user, at(1, 1)) for _ in range(5)]

    capped = await purge_expired_security_records(
        _ctx(db_engine), now=NOW, batch_size=2, max_batches=1
    )
    assert capped["truncated"] == 1
    assert len(await surviving(db_engine, PasswordResetTokenModel, ids)) >= 3

    finished = await purge_expired_security_records(_ctx(db_engine), now=NOW, batch_size=2)
    assert finished["truncated"] == 0
    assert await surviving(db_engine, PasswordResetTokenModel, ids) == set()


@pytest.mark.integration
async def test_an_invalid_retention_setting_raises_before_anything_is_deleted(
    db_engine: AsyncEngine,
) -> None:
    """No fallback (BR-133). The global setting is restored whatever happens."""
    user = await new_user(db_engine)
    doomed = await login_session(db_engine, user, at(1, 1), None)
    key = "session_retention_period"
    async with db_engine.begin() as conn:
        original = await conn.scalar(text("SELECT value FROM settings WHERE key = :k"), {"k": key})
        await conn.execute(
            text("UPDATE settings SET value = '5'::jsonb WHERE key = :k"), {"k": key}
        )
    try:
        with pytest.raises(InvalidSettingValueError):
            await purge_expired_security_records(_ctx(db_engine), now=NOW)
        assert await surviving(db_engine, SessionModel, [doomed]) == {doomed}
    finally:
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
                {"v": json.dumps(original), "k": key},
            )
    await purge_expired_security_records(_ctx(db_engine), now=NOW)
    assert await surviving(db_engine, SessionModel, [doomed]) == set()


@pytest.mark.integration
async def test_counts_cover_at_least_our_rows(db_engine: AsyncEngine) -> None:
    user = await new_user(db_engine)
    await verification_token(db_engine, user, at(1, 1))
    await reset_token(db_engine, user, at(1, 1))
    await login_session(db_engine, user, at(1, 1), None)
    result = await purge_expired_security_records(_ctx(db_engine), now=NOW)
    assert result["verification_tokens"] >= 1
    assert result["password_reset_tokens"] >= 1
    assert result["sessions"] >= 1


@pytest.mark.integration
async def test_retention_follows_an_edited_setting(db_engine: AsyncEngine) -> None:
    """BR-133: an admin's PATCH changes the cutoff without a deploy."""
    user = await new_user(db_engine)
    nine_days_past = await verification_token(db_engine, user, NOW - timedelta(days=9))
    key = "security_token_retention_period"
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE settings SET value = '864000'::jsonb WHERE key = :k"), {"k": key}
        )
    try:
        await purge_expired_security_records(_ctx(db_engine), now=NOW)  # 10 d retention
        assert await surviving(db_engine, VerificationTokenModel, [nine_days_past]) == {
            nine_days_past
        }
    finally:
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE settings SET value = '604800'::jsonb WHERE key = :k"), {"k": key}
            )
    await purge_expired_security_records(_ctx(db_engine), now=NOW)  # back to 7 d
    assert await surviving(db_engine, VerificationTokenModel, [nine_days_past]) == set()


def test_the_worker_runs_it_daily_without_a_startup_run() -> None:
    assert purge_expired_security_records in FUNCTIONS
    [job] = [j for j in CRON_JOBS if j.coroutine is purge_expired_security_records]
    assert job.run_at_startup is False
    assert job.day is None and (job.hour, job.minute) == (3, 29)
