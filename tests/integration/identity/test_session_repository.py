import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.infrastructure.models import SessionModel
from app.identity.infrastructure.repositories import SessionRepository, UserRepository


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


async def _make_user(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(email=_unique_email(), password_hash="not-a-real-hash")
    return user.id


@pytest.mark.integration
async def test_add_and_reload_round_trips_every_field(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _make_user(session_factory)
    expires_at = datetime.now(UTC) + timedelta(days=30)

    async with session_factory() as db, db.begin():
        created = await SessionRepository(db).add(
            session_id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=uuid.uuid4().hex,
            expires_at=expires_at,
            ip_hash="hashed-ip",
            user_agent="pytest",
        )

    async with session_factory() as db:
        loaded = await SessionRepository(db).get_for_update(created.id)

    assert loaded is not None
    assert loaded.user_id == user_id
    assert loaded.token_version == 1  # server default
    assert loaded.revoked_at is None
    assert loaded.rotated_at is None
    assert loaded.reuse_detected_at is None
    assert loaded.ip_hash == "hashed-ip"
    assert loaded.user_agent == "pytest"
    assert loaded.is_live(datetime.now(UTC))


@pytest.mark.integration
async def test_save_persists_rotation(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _make_user(session_factory)
    now = datetime.now(UTC)

    async with session_factory() as db, db.begin():
        created = await SessionRepository(db).add(
            session_id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=uuid.uuid4().hex,
            expires_at=now + timedelta(days=30),
            ip_hash=None,
            user_agent=None,
        )

    new_hash = uuid.uuid4().hex
    async with session_factory() as db, db.begin():
        repo = SessionRepository(db)
        loaded = await repo.get_for_update(created.id)
        assert loaded is not None
        loaded.rotate(new_token_hash=new_hash, at=now)
        await repo.save(loaded)

    async with session_factory() as db:
        reloaded = await SessionRepository(db).get_for_update(created.id)

    assert reloaded is not None
    assert reloaded.refresh_token_hash == new_hash
    assert reloaded.token_version == 2
    assert reloaded.rotated_at is not None
    assert reloaded.last_used_at is not None


@pytest.mark.integration
async def test_rotation_does_not_extend_the_session_deadline(db_engine: AsyncEngine) -> None:
    """A stolen-and-refreshed session must still die on its original deadline."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _make_user(session_factory)
    now = datetime.now(UTC)
    deadline = now + timedelta(days=30)

    async with session_factory() as db, db.begin():
        created = await SessionRepository(db).add(
            session_id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=uuid.uuid4().hex,
            expires_at=deadline,
            ip_hash=None,
            user_agent=None,
        )

    async with session_factory() as db, db.begin():
        repo = SessionRepository(db)
        loaded = await repo.get_for_update(created.id)
        assert loaded is not None
        loaded.rotate(new_token_hash=uuid.uuid4().hex, at=now)
        await repo.save(loaded)

    async with session_factory() as db:
        reloaded = await SessionRepository(db).get_for_update(created.id)

    assert reloaded is not None
    assert reloaded.expires_at == created.expires_at


@pytest.mark.integration
async def test_refresh_token_hash_is_unique_at_the_database(db_engine: AsyncEngine) -> None:
    """An application-level check would lose this race; the constraint cannot."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _make_user(session_factory)
    shared_hash = uuid.uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(days=30)

    async with session_factory() as db, db.begin():
        await SessionRepository(db).add(
            session_id=uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=shared_hash,
            expires_at=expires_at,
            ip_hash=None,
            user_agent=None,
        )

    with pytest.raises(IntegrityError):
        async with session_factory() as db, db.begin():
            await SessionRepository(db).add(
                session_id=uuid.uuid4(),
                user_id=user_id,
                refresh_token_hash=shared_hash,
                expires_at=expires_at,
                ip_hash=None,
                user_agent=None,
            )


@pytest.mark.integration
async def test_token_version_must_stay_positive(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _make_user(session_factory)

    with pytest.raises(IntegrityError):
        async with session_factory() as db, db.begin():
            db.add(
                SessionModel(
                    user_id=user_id,
                    refresh_token_hash=uuid.uuid4().hex,
                    token_version=0,
                    expires_at=datetime.now(UTC) + timedelta(days=30),
                )
            )


@pytest.mark.integration
async def test_get_for_update_returns_none_for_an_unknown_session(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with session_factory() as db:
        assert await SessionRepository(db).get_for_update(uuid.uuid4()) is None
