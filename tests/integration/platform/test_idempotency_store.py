"""SqlIdempotencyStore against Postgres: every claim transition and the purge (VS-023
plan 3.7). Each test commits its own rows with unique keys; the database is shared."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.domain.idempotency import Conflict, InProgress, NewClaim, Replay
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.integration.deep_support import create_user

pytestmark = pytest.mark.integration

LATER = datetime.now(UTC) + timedelta(hours=24)


async def _claim(
    engine: AsyncEngine,
    user_id: uuid.UUID | None,
    key: str,
    digest: str = "a" * 64,
    expires_at: datetime = LATER,
) -> object:
    async with async_sessionmaker(engine)() as session, session.begin():
        return await SqlIdempotencyStore(session).claim(
            scope="checkout", user_id=user_id, key=key, request_hash=digest, expires_at=expires_at
        )


async def test_a_new_key_is_claimed_in_progress(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    key = uuid.uuid4().hex
    claim = await _claim(db_engine, user.id, key)
    assert isinstance(claim, NewClaim)
    async with db_engine.connect() as conn:
        state = await conn.scalar(
            text("SELECT state FROM idempotency_records WHERE id = :i"), {"i": claim.record_id}
        )
    assert state == "in_progress"


async def test_the_same_request_in_progress_names_its_resource(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    key, order_id = uuid.uuid4().hex, uuid.uuid4()
    first = await _claim(db_engine, user.id, key)
    assert isinstance(first, NewClaim)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        await SqlIdempotencyStore(session).attach(first.record_id, resource_id=order_id)
    assert await _claim(db_engine, user.id, key) == InProgress(order_id)


async def test_a_completed_request_replays_its_response(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    key = uuid.uuid4().hex
    first = await _claim(db_engine, user.id, key)
    assert isinstance(first, NewClaim)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        await SqlIdempotencyStore(session).complete(
            first.record_id, status_code=201, body={"order": {"order_number": "B3D-X"}}
        )
    assert await _claim(db_engine, user.id, key) == Replay(
        201, {"order": {"order_number": "B3D-X"}}
    )


async def test_a_different_body_under_the_same_key_conflicts(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    key = uuid.uuid4().hex
    assert isinstance(await _claim(db_engine, user.id, key), NewClaim)
    assert await _claim(db_engine, user.id, key, digest="b" * 64) == Conflict()


async def test_keys_are_scoped_per_user(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    alice, bob = await create_user(db_session), await create_user(db_session)
    key = uuid.uuid4().hex
    assert isinstance(await _claim(db_engine, alice.id, key), NewClaim)
    assert isinstance(await _claim(db_engine, bob.id, key), NewClaim)


async def test_a_null_user_still_deduplicates(db_engine: AsyncEngine) -> None:
    key = uuid.uuid4().hex
    assert isinstance(await _claim(db_engine, None, key), NewClaim)
    assert await _claim(db_engine, None, key) == InProgress(None)


async def test_a_rolled_back_claim_leaves_the_key_free(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    key = uuid.uuid4().hex
    async with async_sessionmaker(db_engine)() as session:
        claim = await SqlIdempotencyStore(session).claim(
            scope="checkout", user_id=user.id, key=key, request_hash="a" * 64, expires_at=LATER
        )
        assert isinstance(claim, NewClaim)
        await session.rollback()
    assert isinstance(await _claim(db_engine, user.id, key), NewClaim)


async def test_the_purge_deletes_only_expired_claims(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    past = datetime.now(UTC) - timedelta(minutes=1)
    old = [await _claim(db_engine, user.id, uuid.uuid4().hex, expires_at=past) for _ in range(3)]
    live = await _claim(db_engine, user.id, uuid.uuid4().hex)
    assert all(isinstance(c, NewClaim) for c in [*old, live])
    async with async_sessionmaker(db_engine)() as session, session.begin():
        removed = await SqlIdempotencyStore(session).purge_expired(now=datetime.now(UTC), limit=2)
    assert removed == 2
    async with async_sessionmaker(db_engine)() as session, session.begin():
        await SqlIdempotencyStore(session).purge_expired(now=datetime.now(UTC), limit=1000)
    ids = [c.record_id for c in [*old, live] if isinstance(c, NewClaim)]
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id FROM idempotency_records WHERE id = ANY(:ids)"), {"ids": ids}
        )
        assert [row.id for row in rows] == [ids[-1]]


async def test_the_purge_skips_a_locked_claim(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    past = datetime.now(UTC) - timedelta(minutes=1)
    held = await _claim(db_engine, user.id, uuid.uuid4().hex, expires_at=past)
    assert isinstance(held, NewClaim)
    async with db_engine.connect() as locker:
        await locker.execute(
            text("SELECT id FROM idempotency_records WHERE id = :i FOR UPDATE"),
            {"i": held.record_id},
        )
        async with async_sessionmaker(db_engine)() as session, session.begin():
            await SqlIdempotencyStore(session).purge_expired(now=datetime.now(UTC), limit=1000)
        async with db_engine.connect() as conn:
            still = await conn.scalar(
                text("SELECT count(*) FROM idempotency_records WHERE id = :i"),
                {"i": held.record_id},
            )
        assert still == 1
        await locker.rollback()
