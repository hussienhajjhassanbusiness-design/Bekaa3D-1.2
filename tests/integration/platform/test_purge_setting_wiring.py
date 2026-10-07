"""The unverified-account purge job now reads its retention from the database.

Before VS-007 the period was `unverified_account_retention_days: int = 30` in
`config.py` - a hardcoded business parameter, which is exactly what BR-133
forbids. This slice moves the control into `settings` and removes the constant.

Two properties matter, and they pull in opposite directions: the job must behave
*identically* on deployment (the seed is 30 days), and it must follow the
setting the moment an administrator changes it, with no restart.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.infrastructure.models import UserModel
from app.jobs.purge_unverified import purge_unverified_accounts
from app.platform.domain.exceptions import SettingNotFoundError
from app.platform.domain.settings_registry import REGISTRY
from app.platform.infrastructure.models import SettingModel

KEY = "unverified_account_purge_period"


async def _unverified_user(
    session_factory: async_sessionmaker[AsyncSession], *, age_days: int
) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = UserModel(
            email=f"test-{uuid.uuid4().hex}@example.com",
            password_hash="not-a-real-hash",
            created_at=datetime.now(UTC) - timedelta(days=age_days),
        )
        db.add(user)
        await db.flush()
        return user.id


async def _still_exists(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> bool:
    async with session_factory() as db:
        return await db.get(UserModel, user_id) is not None


async def _set_period(session_factory: async_sessionmaker[AsyncSession], seconds: int) -> None:
    async with session_factory() as db, db.begin():
        row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
        assert row is not None
        row.value = seconds


@pytest.mark.integration
async def test_the_seeded_period_preserves_the_previous_thirty_day_behaviour(
    db_engine: AsyncEngine,
) -> None:
    """Deployment must change nothing. 30 days is exactly what the constant was."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    assert REGISTRY[KEY].default == 2_592_000

    old = await _unverified_user(session_factory, age_days=40)
    recent = await _unverified_user(session_factory, age_days=20)

    await purge_unverified_accounts({"session_factory": session_factory})

    assert not await _still_exists(session_factory, old)
    assert await _still_exists(session_factory, recent)


@pytest.mark.integration
async def test_changing_the_setting_changes_the_job_with_no_restart(
    db_engine: AsyncEngine,
) -> None:
    """The point of the whole slice (BR-133, SRS 15.4: "settings rather than
    constants specifically so operational changes never require a deployment").

    The same account survives one run and is purged by the next, with nothing
    between them but an edit to the setting - no reload, no new process.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user = await _unverified_user(session_factory, age_days=10)

    try:
        await purge_unverified_accounts({"session_factory": session_factory})
        assert await _still_exists(session_factory, user), "10 days is inside the 30-day period"

        await _set_period(session_factory, 604_800)  # 7 days

        await purge_unverified_accounts({"session_factory": session_factory})
        assert not await _still_exists(session_factory, user)
    finally:
        default = REGISTRY[KEY].default
        assert isinstance(default, int)
        await _set_period(session_factory, default)


@pytest.mark.integration
async def test_the_job_fails_loudly_when_the_setting_is_missing(
    db_engine: AsyncEngine,
) -> None:
    """No silent fallback to 30 days.

    A constant quietly substituted here would reintroduce exactly the hardcoded
    business parameter BR-133 forbids - and worse, it would keep deleting
    accounts on a schedule nobody had approved, invisibly. Failing is the
    observable outcome: the worker logs it and cron-liveness monitoring notices.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    survivor = await _unverified_user(session_factory, age_days=400)

    async with session_factory() as db, db.begin():
        row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
        assert row is not None
        saved = row.value
        await db.delete(row)

    try:
        with pytest.raises(SettingNotFoundError):
            await purge_unverified_accounts({"session_factory": session_factory})
        # And nothing was deleted on the way to failing.
        assert await _still_exists(session_factory, survivor)
    finally:
        async with session_factory() as db, db.begin():
            db.add(
                SettingModel(
                    key=KEY,
                    type=REGISTRY[KEY].type,
                    value=saved,
                    description="restored by test",
                )
            )
