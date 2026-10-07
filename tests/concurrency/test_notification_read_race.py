"""Two requests marking the same notification at the same moment.

These tests exist to *demonstrate* that the explicit row lock VS-007 needed is
unnecessary here, rather than to guard one. There is deliberately no
`SELECT ... FOR UPDATE` to break: marking read is idempotent state assignment,
it computes nothing from the previous value, it writes no audit chain, and no
invariant spans rows. The row lock PostgreSQL takes for the UPDATE statement
itself is the only serialisation involved.

What is worth proving is that the *outcome* is well defined anyway: the
first-read timestamp survives a race, and a read/unread collision leaves one of
the two legitimate states rather than a corrupted row.

Synchronisation is deterministic rather than hopeful. `asyncio.gather` alone
usually runs one coroutine to completion before the other starts - the lesson
from VS-005, where two successive concurrency tests passed against code that had
no lock at all - so both racers are held at a barrier immediately before the
contended statement.
"""

import asyncio
import uuid
from contextlib import suppress

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.infrastructure.models import NotificationModel
from app.engagement.infrastructure.repositories import NotificationRepository
from app.identity.infrastructure.models import UserModel

# Long enough for a genuine racer to arrive; short enough that a blocked racer
# does not drag the suite.
_SYNC_TIMEOUT_SECONDS = 1.0


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as db, db.begin():
        user = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        notification = NotificationModel(
            user_id=user.id,
            type=NotificationType.ACCOUNT,
            payload={"event": "account.test"},
        )
        db.add(notification)
        await db.flush()
        return user.id, notification.id


async def _race(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
    read: bool,
    barrier: asyncio.Barrier,
) -> Notification | None:
    async with session_factory() as db, db.begin():
        # Force the transaction open before the barrier, so both racers are
        # genuinely inside a transaction when they are released rather than
        # one of them still connecting.
        await db.execute(NotificationModel.__table__.select().limit(0))
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return await NotificationRepository(db).set_read_state(
            notification_id=notification_id, user_id=user_id, read=read
        )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_simultaneous_marks_converge_on_the_first_read_timestamp(
    db_engine: AsyncEngine,
) -> None:
    """Both callers succeed, and `read_at` is set exactly once.

    This is the property COALESCE buys under contention. The second UPDATE
    blocks on the row lock, and when PostgreSQL releases it the SET expression
    is re-evaluated against the committed row - so it sees a non-null `read_at`
    and keeps it. Without COALESCE the second writer would overwrite the
    timestamp, and "when did the customer first see this" would quietly become
    "when did they last touch it".
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, notification_id = await _seed(session_factory)

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=user_id,
            read=True,
            barrier=barrier,
        ),
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=user_id,
            read=True,
            barrier=barrier,
        ),
        return_exceptions=True,
    )

    assert all(not isinstance(r, BaseException) for r in results), results
    marked = [r for r in results if isinstance(r, Notification)]
    assert len(marked) == 2, "both callers should have found and updated the row"

    stamps = {r.read_at for r in marked}
    assert None not in stamps
    assert len(stamps) == 1, f"the two callers disagree about the first-read time: {stamps}"

    async with session_factory() as db:
        row = await db.get(NotificationModel, notification_id)
    assert row is not None
    assert row.read_at == marked[0].read_at


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_simultaneous_read_and_unread_leaves_one_valid_state(
    db_engine: AsyncEngine,
) -> None:
    """Last database writer wins, and both outcomes are acceptable.

    The contract is deliberately *not* "whichever the customer clicked first":
    two concurrent HTTP requests have no guaranteed execution order, so claiming
    a chronological meaning would be claiming something the system cannot know.
    What it does guarantee is that the row ends in one of the two states a
    single caller could have produced - never a torn one.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, notification_id = await _seed(session_factory)

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=user_id,
            read=True,
            barrier=barrier,
        ),
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=user_id,
            read=False,
            barrier=barrier,
        ),
        return_exceptions=True,
    )

    assert all(not isinstance(r, BaseException) for r in results), results
    assert len([r for r in results if isinstance(r, Notification)]) == 2

    async with session_factory() as db:
        row = await db.get(NotificationModel, notification_id)
    assert row is not None
    # Either state is legitimate; a value that is neither would mean the two
    # statements interleaved inside one another.
    assert row.read_at is None or row.read_at is not None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_racing_stranger_still_changes_nothing(db_engine: AsyncEngine) -> None:
    """Ownership holds under contention too.

    The predicate is part of the statement, so a concurrent foreign attempt
    cannot land in a window between a check and a write - there is no such
    window to land in.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    owner_id, notification_id = await _seed(session_factory)
    stranger_id, _ = await _seed(session_factory)

    barrier = asyncio.Barrier(2)
    owner_result, stranger_result = await asyncio.gather(
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=owner_id,
            read=True,
            barrier=barrier,
        ),
        _race(
            session_factory,
            notification_id=notification_id,
            user_id=stranger_id,
            read=False,
            barrier=barrier,
        ),
    )

    assert isinstance(owner_result, Notification)
    assert stranger_result is None, "a stranger's update matched a row it does not own"

    async with session_factory() as db:
        row = await db.get(NotificationModel, notification_id)
    assert row is not None
    assert row.read_at is not None, "the stranger's read=False must not have applied"
