"""ADR-050: simultaneous failures for one account and IP share one row, and none is lost.
Without the advisory lock each racer finds no row, inserts its own, and the volume cap fails."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.database import make_session_factory
from app.identity.infrastructure.failed_login_audit import ACTION, record_failed_login
from app.platform.infrastructure.models import AuditLogModel
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user

RACERS = 8


@pytest.mark.concurrency
@pytest.mark.integration
async def test_parallel_failures_land_on_one_row_with_the_full_count(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session)
    user_id, email = user.id, user.email
    ip_hash = uuid.uuid4().hex
    plain = make_session_factory(db_engine)
    barrier = asyncio.Barrier(RACERS)

    @asynccontextmanager
    async def together() -> AsyncIterator[AsyncSession]:
        async with plain() as session:
            await meet_or_fail(barrier)
            yield session

    factory = cast(async_sessionmaker[AsyncSession], together)
    await asyncio.gather(
        *(
            record_failed_login(
                factory,
                email=email,
                ip_hash=ip_hash,
                request_id=None,
                reason="invalid_credentials",
            )
            for _ in range(RACERS)
        )
    )
    db_session.expire_all()
    rows = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.action == ACTION, AuditLogModel.entity_id == user_id
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].after_data is not None
    assert rows[0].after_data["count"] == RACERS
