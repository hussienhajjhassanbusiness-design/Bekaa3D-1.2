"""VS-011 / BUG-38: the active administrator set can never be emptied, even by a race.

Two administrators deactivating *each other* lock only their own target row, each
still counts the other as active, and both would succeed - leaving none. The
advisory lock in `UserRepository.lock_administrator_set` serialises them. The
racers are released from a barrier placed after the contended row read (see
`test_admin_user_activation_race.py`), so against code with no serialisation both
would reach the count together; the barrier times out harmlessly in the locked
case, where the second racer is blocked and never arrives.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.set_user_active import SetUserActive
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import LastActiveAdministratorError
from app.identity.infrastructure.models import UserModel
from app.identity.infrastructure.repositories import SessionRepository
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter as AuditWriter
from tests.concurrency.test_admin_user_activation_race import _SyncedUserRepository

_PASSWORD_HASH = "x"


async def _seed_sole_pair(factory: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, uuid.UUID]:
    """Two active administrators, and nobody else: the shared test database holds
    administrators left by earlier tests, so they are stood down first."""
    async with factory() as db, db.begin():
        await db.execute(
            update(UserModel).where(UserModel.role == UserRole.ADMIN).values(is_active=False)
        )
        rows = [
            UserModel(
                email=f"last-admin-{uuid.uuid4().hex}@example.com",
                password_hash=_PASSWORD_HASH,
                role=UserRole.ADMIN,
                email_verified_at=datetime.now(UTC),
            )
            for _ in range(2)
        ]
        db.add_all(rows)
        await db.flush()
        return rows[0].id, rows[1].id


async def _deactivate(
    factory: async_sessionmaker[AsyncSession],
    target: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> object:
    async with factory() as db, db.begin():
        return await SetUserActive(
            _SyncedUserRepository(db, barrier), SessionRepository(db), AuditWriter(db)
        ).execute(
            user_id=target, is_active=False, actor_user_id=actor, request_id=None, ip_hash=None
        )


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("round_", range(3))
async def test_two_administrators_deactivating_each_other_leave_exactly_one(
    db_engine: AsyncEngine, round_: int
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    a, b = await _seed_sole_pair(factory)
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        _deactivate(factory, target=b, actor=a, barrier=barrier),
        _deactivate(factory, target=a, actor=b, barrier=barrier),
        return_exceptions=True,
    )

    refused = [r for r in results if isinstance(r, LastActiveAdministratorError)]
    succeeded = [r for r in results if getattr(r, "changed", False)]
    assert len(succeeded) == 1 and len(refused) == 1, results

    async with factory() as db:
        active = list(
            await db.scalars(
                select(UserModel.id).where(UserModel.id.in_([a, b]), UserModel.is_active.is_(True))
            )
        )
        deactivations = list(
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.entity_id.in_([a, b]),
                    AuditLogModel.action == "user.deactivated",
                )
            )
        )
    assert len(active) == 1, "exactly one administrator must remain active"
    assert len(deactivations) == 1, "the refused request must leave no audit row"


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("round_", range(3))
async def test_three_administrators_deactivating_in_a_ring_never_reach_zero(
    db_engine: AsyncEngine, round_: int
) -> None:
    """A deactivates B, B deactivates C, C deactivates A - all at once. Each
    racer locks a different row, so only the advisory lock stands between this
    and an empty administrator set."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    a, b = await _seed_sole_pair(factory)
    async with factory() as db, db.begin():
        third = UserModel(
            email=f"last-admin-{uuid.uuid4().hex}@example.com",
            password_hash=_PASSWORD_HASH,
            role=UserRole.ADMIN,
            email_verified_at=datetime.now(UTC),
        )
        db.add(third)
        await db.flush()
        c = third.id
    barrier = asyncio.Barrier(3)

    results = await asyncio.gather(
        _deactivate(factory, target=b, actor=a, barrier=barrier),
        _deactivate(factory, target=c, actor=b, barrier=barrier),
        _deactivate(factory, target=a, actor=c, barrier=barrier),
        return_exceptions=True,
    )

    unexpected = [
        r
        for r in results
        if isinstance(r, BaseException) and not isinstance(r, LastActiveAdministratorError)
    ]
    assert not unexpected, unexpected
    assert sum(isinstance(r, LastActiveAdministratorError) for r in results) == 1, results
    async with factory() as db:
        active = await db.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
                UserModel.anonymized_at.is_(None),
                UserModel.deleted_at.is_(None),
            )
        )
    assert active == 1, "the active administrator set must never be emptied"
