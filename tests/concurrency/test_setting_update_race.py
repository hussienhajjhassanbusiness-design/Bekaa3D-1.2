"""Two administrators editing the same setting at the same moment.

FR-18 requires "deterministic conflict or last-commit behavior with both
attempts audited". This is the last-commit half, and the property worth testing
is not that both requests succeed - they would succeed with no lock at all -
but that the **audit trail describes what actually happened**.

With the row lock, a race produces:

    admin A:  10 -> 20
    admin B:  20 -> 30

Without it, both read 10 first and the log claims:

    admin A:  10 -> 20
    admin B:  10 -> 30

which is a history that never occurred: nobody ever changed the value from 10 to
30. An investigator reading that log would draw the wrong conclusion about who
overwrote whom.

Synchronisation is deterministic rather than hopeful. `asyncio.gather` alone
usually runs one coroutine to completion before the other starts - the lesson
from VS-005, where two successive concurrency tests passed against code that had
no lock at all - so the racers are released from a barrier placed immediately
after the contended read.
"""

import asyncio
import uuid
from contextlib import suppress

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.application.commands.update_setting import UpdateSetting
from app.platform.domain.entities import Setting
from app.platform.infrastructure.models import AuditLogModel, SettingModel
from app.platform.infrastructure.repositories import AuditLogRepository, SettingRepository

KEY = "daily_download_cap"

# Long enough for a genuine racer to arrive; short enough that the locked case -
# where the second racer is blocked inside PostgreSQL and cannot arrive - does
# not drag the suite.
_SYNC_TIMEOUT_SECONDS = 1.0


class _SyncedSettingRepository(SettingRepository):
    """Holds every racer at the point between reading the row and writing it.

    The window under test is read -> decide -> write, and it only demonstrates
    anything if both transactions are inside it together. The timeout is what
    makes the sync point safe in both directions:

    - **Unlocked:** both complete their read, both reach the barrier, both are
      released, and both write from the same stale "before". The race is real
      and the assertion below fails, as it must.
    - **Locked:** the second racer is still blocked inside PostgreSQL on
      `SELECT ... FOR UPDATE` and never arrives. The first waits, times out,
      commits; the lock releases; the second then reads the committed row.

    Without the timeout the locked case would hang on a barrier that can never
    fill.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def _sync(self, value: Setting | None) -> Setting | None:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return value

    async def get_by_key_for_update(self, key: str) -> Setting | None:
        return await self._sync(await super().get_by_key_for_update(key))

    async def get_by_key(self, key: str) -> Setting | None:
        """Overridden too, and not for symmetry.

        If only the locking reader paused here, swapping the command back to the
        plain read - precisely the regression this file guards - would bypass
        the sync point entirely, the racers would never overlap, and the test
        would pass against the broken code.
        """
        return await self._sync(await super().get_by_key(key))


async def _update(
    session_factory: async_sessionmaker[AsyncSession],
    value: int,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> None:
    async with session_factory() as db, db.begin():
        await UpdateSetting(
            settings_repo=_SyncedSettingRepository(db, barrier),
            audit_repo=AuditLogRepository(db),
        ).execute(key=KEY, value=value, actor_user_id=actor, request_id=None, ip_hash=None)


async def _seed_admin(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    from app.identity.infrastructure.models import UserModel

    async with session_factory() as db, db.begin():
        admin = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(admin)
        await db.flush()
        return admin.id


async def _reset_to(session_factory: async_sessionmaker[AsyncSession], value: int) -> None:
    async with session_factory() as db, db.begin():
        row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
        assert row is not None
        row.value = value


async def _audit_transitions(
    session_factory: async_sessionmaker[AsyncSession], actors: tuple[uuid.UUID, ...]
) -> list[tuple[object, object]]:
    """The `key` transitions audited by these specific actors.

    Scoped by actor, and deliberately **not** ordered by `created_at`.

    Both details were bugs. The audit table is shared across the whole test
    session, so reading every `setting.updated` row for this key picked up
    whatever `test_admin_settings.py` had written, depending on collection
    order. And `created_at` is `func.now()`, which in PostgreSQL is the
    *transaction start* time - not the commit time. Two transactions that race
    by microseconds can therefore carry timestamps in the opposite order to the
    order they committed in, which made an ordering-based assertion pass or fail
    by luck. The actor ids are freshly created per test, so they isolate
    exactly; the caller asserts on the shape of the set instead of its order.
    """
    async with session_factory() as db:
        rows = (
            await db.scalars(
                select(AuditLogModel)
                .where(AuditLogModel.action == "setting.updated")
                .where(AuditLogModel.actor_user_id.in_(actors))
            )
        ).all()
    return [
        (row.before_data["value"], row.after_data["value"])
        for row in rows
        if row.before_data is not None
        and row.after_data is not None
        and row.before_data.get("key") == KEY
    ]


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_administrators_racing_produce_a_truthful_audit_chain(
    db_engine: AsyncEngine,
) -> None:
    """The audit rows must chain: one transition ends where the next begins.

    Either ordering is acceptable - last-commit means whoever gets the lock
    second wins - so the assertion is on the *shape* of the history rather than
    on which administrator won.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    admin_a = await _seed_admin(session_factory)
    admin_b = await _seed_admin(session_factory)
    await _reset_to(session_factory, 10)

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _update(session_factory, 20, admin_a, barrier),
        _update(session_factory, 30, admin_b, barrier),
        return_exceptions=True,
    )
    assert all(not isinstance(r, BaseException) for r in results), results

    transitions = await _audit_transitions(session_factory, (admin_a, admin_b))
    assert len(transitions) == 2, f"expected one audit row per administrator, got {transitions}"

    # Reconstructed from the set rather than read off in row order, because the
    # rows carry no trustworthy record of which committed first (see
    # _audit_transitions). The chain itself is the proof: exactly one update
    # replaced the starting value, and the other replaced *that one's result*.
    opening = [t for t in transitions if t[0] == 10]
    assert len(opening) == 1, (
        "exactly one update should have replaced the starting value of 10; "
        f"got {transitions} - both administrators read 10, so they did not serialise"
    )
    first = opening[0]
    second = next(t for t in transitions if t is not first)

    assert second[0] == first[1], (
        f"the second administrator recorded a 'before' of {second[0]!r} "
        f"while the value was actually {first[1]!r} - the two updates did not serialise"
    )

    async with session_factory() as db:
        row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
    assert row is not None
    assert row.value == second[1], "the stored value must be whatever committed last"
    assert row.value in (20, 30)

    await _reset_to(session_factory, 20)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_no_op_update_is_audited_without_touching_the_metadata(
    db_engine: AsyncEngine,
) -> None:
    """Setting a value to what it already is.

    FR-18 asks for both of two concurrent attempts to be audited, and under
    last-commit semantics the second frequently *is* a no-op - so it produces an
    audit row with equal before/after. But nothing changed, so `updated_at` and
    `updated_by` must not move: they describe when the value last actually
    changed, and bumping them would misattribute the change to whoever ran the
    no-op.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    admin = await _seed_admin(session_factory)
    await _reset_to(session_factory, 20)

    async with session_factory() as db:
        before_row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
        assert before_row is not None
        stamp_before = before_row.updated_at
        actor_before = before_row.updated_by

    async with session_factory() as db, db.begin():
        result = await UpdateSetting(
            settings_repo=SettingRepository(db),
            audit_repo=AuditLogRepository(db),
        ).execute(key=KEY, value=20, actor_user_id=admin, request_id=None, ip_hash=None)
    assert result.changed is False

    async with session_factory() as db:
        after_row = await db.scalar(select(SettingModel).where(SettingModel.key == KEY))
    assert after_row is not None
    assert after_row.updated_at == stamp_before
    assert after_row.updated_by == actor_before

    # Scoped to this test's own administrator, so it cannot be satisfied - or
    # broken - by a row another test happened to write for the same key.
    transitions = await _audit_transitions(session_factory, (admin,))
    assert transitions == [(20, 20)], (
        f"a no-op must still be audited exactly once, with equal before/after; got {transitions}"
    )
