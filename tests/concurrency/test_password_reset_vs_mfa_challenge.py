"""A password reset racing the redemption of a challenge issued before it.

The postcondition is one sentence: once a reset has returned successfully, no
challenge issued before it can result in a usable session. Sequentially that is
easy - the epoch check refuses the challenge. Concurrently there are two
orderings, and the requirement is that *both* end in the same place:

- **Reset commits first.** The challenge redemption must be refused outright.
- **Redemption commits first.** It may legitimately create a session - it got
  there before the reset did - but the reset must then find that session and
  revoke it. A reset that returns 204 while a session it did not know about is
  still live has not done what SEC-08 asks.

What must never happen is the third ordering: the redemption inserting its
session *after* the reset's revocation UPDATE has already run. That leaves a
live session minted from a pre-reset challenge, which is the exact hole this
file exists to keep closed.

Both operations take a `SELECT ... FOR UPDATE` on the user row
(`UserRepository.get_by_id_for_update`), which is what removes that third
ordering: neither can interleave with the other. The lock is a database
mechanism, so this is an integration test against real PostgreSQL - a mock
would assert nothing about it.

On the synchronisation: bare `asyncio.gather` does not reliably produce a race
(one coroutine usually runs to completion before the other starts), so the
racers are released from a barrier *inside* their transactions and immediately
before the contended read. That is the lesson from VS-005's TOTP replay work,
where two successive versions of a concurrency test went green against code
that had no lock at all.
"""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.confirm_password_reset import ConfirmPasswordReset
from app.identity.application.commands.mfa_complete_login import CompleteMfaLogin
from app.identity.application.security.password_hasher import verify_password
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.domain.entities import Session
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import (
    PasswordResetTokenModel,
    SessionModel,
    UserModel,
)
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter as AuditWriter

NEW_PASSWORD = "the-password-the-reset-installs"

# Long enough for a genuine racer to arrive, short enough that the blocked case
# - where the second racer is stuck inside PostgreSQL and cannot arrive - does
# not drag the suite out.
_SYNC_TIMEOUT_SECONDS = 1.0


async def _current_epoch(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> int:
    """The account's epoch as the database holds it - the authority, not a
    cache. Read in its own transaction so it reflects committed state."""
    async with session_factory() as db:
        epoch = await UserRepository(db).get_auth_epoch(user_id)
    assert epoch is not None
    return epoch


async def _seed_admin_with_reset_token(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    """An administrator holding a live, unredeemed password reset token."""
    raw_token = generate_raw_token()
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com", password_hash="not-a-real-hash"
        )
        model = await db.get(UserModel, user.id)
        assert model is not None
        model.role = UserRole.ADMIN
        model.email_verified_at = datetime.now(UTC)
        await PasswordResetTokenRepository(db).add(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    return user.id, raw_token


class _SyncedUserRepository(UserRepository):
    """Holds every racer at the point just after the contended row read.

    The window under test is read -> decide -> write, and it only demonstrates
    anything if both transactions are inside it together. The timeout is what
    makes the sync point safe in both directions:

    - **Unlocked:** both racers complete their read, both reach the barrier,
      both are released, and both write from stale state. The race is real and
      the assertions below fail, as they must.
    - **Locked:** the second racer is still blocked inside PostgreSQL on
      `SELECT ... FOR UPDATE` and never arrives. The first waits, times out,
      proceeds and commits; the lock releases; the second then reads the row the
      first one already changed.

    Without the timeout the locked case would hang on a barrier that can never
    fill.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def _sync(self, value: object) -> object:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return value

    async def get_by_id_for_update(self, user_id: uuid.UUID):  # type: ignore[no-untyped-def]
        return await self._sync(await super().get_by_id_for_update(user_id))

    async def get_by_id(self, user_id: uuid.UUID):  # type: ignore[no-untyped-def]
        """Overridden too, and not for symmetry.

        If only the locking reader paused here, swapping either command back to
        the plain read - precisely the regression this file guards - would
        bypass the sync point, the racers would never overlap, and the test
        would pass against the broken code."""
        return await self._sync(await super().get_by_id(user_id))


class _LateInsertingSessionRepository(SessionRepository):
    """Forces the redeemer's session INSERT to land *after* the reset's
    revocation UPDATE.

    This is what makes the test mean something. Aligning the two reads on a
    barrier is not enough on its own: after the barrier the reset spends ~80ms
    inside Argon2 before it reaches `revoke_all_for_user`, while the redeemer
    reaches its INSERT almost immediately. Left to run, the redeemer therefore
    commits first in *both* the locked and the unlocked build, the revocation
    sweeps up its session either way, and the test passes against code with no
    lock at all - decorative, in exactly the way VS-005's first two concurrency
    tests were.

    Waiting for the revocation inverts that. The dangerous ordering becomes the
    one the unlocked build actually takes, and the lock is the only thing that
    can prevent it:

    - **Unlocked:** the reset is not blocked, so it bumps the epoch and revokes
      while no session exists yet, then sets the event. The redeemer - which
      passed its epoch check *before* waiting - wakes up and inserts a session
      nothing will ever revoke. `live == 1`, and the test fails.
    - **Locked:** one of the two holds the user row and the other cannot reach
      this point at all, so the wait times out harmlessly and the orderings
      collapse to the two safe ones.
    """

    def __init__(self, session: AsyncSession, revoked: asyncio.Event) -> None:
        super().__init__(session)
        self._revoked = revoked

    async def add(self, **kwargs: Any) -> Session:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._revoked.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return await super().add(**kwargs)


class _AnnouncingSessionRepository(SessionRepository):
    """The reset's side of that handshake: announce the moment revocation has
    run, so the redeemer above can aim its INSERT just after it."""

    def __init__(self, session: AsyncSession, revoked: asyncio.Event) -> None:
        super().__init__(session)
        self._revoked = revoked

    async def revoke_all_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
        count = await super().revoke_all_for_user(user_id=user_id, at=at)
        self._revoked.set()
        return count


async def _reset(
    session_factory: async_sessionmaker[AsyncSession],
    raw_token: str,
    barrier: asyncio.Barrier,
    revoked: asyncio.Event,
) -> None:
    async with session_factory() as db, db.begin():
        await ConfirmPasswordReset(
            user_repo=_SyncedUserRepository(db, barrier),
            token_repo=PasswordResetTokenRepository(db),
            session_repo=_AnnouncingSessionRepository(db, revoked),
            audit_writer=AuditWriter(db),
        ).execute(
            raw_token=raw_token,
            new_password=NEW_PASSWORD,
            request_id=None,
            ip_hash=None,
        )


async def _redeem_challenge(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    challenge_epoch: int,
    barrier: asyncio.Barrier,
    revoked: asyncio.Event,
) -> uuid.UUID:
    """Complete a login for a challenge minted at `challenge_epoch`.

    The second factor is assumed already checked - this is the half that mints
    the session, which is the half the reset has to be ordered against.
    """
    async with session_factory() as db, db.begin():
        result = await CompleteMfaLogin(
            user_repo=_SyncedUserRepository(db, barrier),
            session_repo=_LateInsertingSessionRepository(db, revoked),
            audit_writer=AuditWriter(db),
        ).execute(
            user_id=user_id,
            challenge_epoch=challenge_epoch,
            ip_hash=None,
            user_agent=None,
            request_id=None,
        )
        return result.session_id


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_pre_reset_challenge_never_leaves_a_usable_session_behind(
    db_engine: AsyncEngine,
) -> None:
    """The postcondition, asserted against stored state rather than return
    values.

    Either ordering is allowed to win. What is asserted is what the database
    holds once both have finished: the password is the new one, and no session
    reachable from the pre-reset challenge is live.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed_admin_with_reset_token(session_factory)

    # A challenge minted before the reset: it carries the epoch as it stands now.
    challenge_epoch = await _current_epoch(session_factory, user_id)

    barrier = asyncio.Barrier(2)
    revoked = asyncio.Event()
    results = await asyncio.gather(
        _reset(session_factory, raw_token, barrier, revoked),
        _redeem_challenge(session_factory, user_id, challenge_epoch, barrier, revoked),
        return_exceptions=True,
    )
    reset_outcome, redeem_outcome = results

    # The reset must have succeeded either way - the challenge has no business
    # blocking it.
    assert not isinstance(reset_outcome, BaseException), reset_outcome

    async with session_factory() as db:
        user = await db.get(UserModel, user_id)
        live = await db.scalar(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        )
        token = await db.scalar(
            select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user_id)
        )

    assert user is not None
    assert verify_password(password=NEW_PASSWORD, password_hash=user.password_hash)
    assert token is not None and token.used_at is not None

    # The whole point. Whether the redemption was refused or whether it created
    # a session that the reset then revoked, nothing usable survives.
    assert live == 0, (
        "a session minted from a pre-reset MFA challenge is still live "
        f"(redemption outcome: {redeem_outcome!r})"
    )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_reset_wins_and_the_challenge_is_refused(db_engine: AsyncEngine) -> None:
    """The sequential half of the guarantee, stated separately.

    The test above accepts either ordering by design, so on its own it would
    still pass if the epoch check were deleted and every race happened to be won
    by the reset's revocation. This one removes the ambiguity: the reset has
    fully committed before the redemption starts, so there is exactly one
    correct answer and no session may be created at all.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed_admin_with_reset_token(session_factory)
    challenge_epoch = await _current_epoch(session_factory, user_id)

    uncontended = asyncio.Barrier(1)
    already_revoked = asyncio.Event()
    already_revoked.set()
    await _reset(session_factory, raw_token, uncontended, already_revoked)

    with pytest.raises(Exception) as refused:
        await _redeem_challenge(
            session_factory,
            user_id,
            challenge_epoch,
            asyncio.Barrier(1),
            already_revoked,
        )

    async with session_factory() as db:
        live = await db.scalar(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        )

    assert live == 0
    assert refused.value is not None
