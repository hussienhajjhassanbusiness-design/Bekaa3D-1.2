"""A password reset racing the other two paths that mint credentials.

`test_password_reset_vs_mfa_challenge.py` covers MFA completion. These are the
other two, and the invariant is the same one stated three ways:

> No authentication operation that started from a pre-reset credential may
> emerge after the reset carrying the post-reset `auth_epoch`.

For **login**, the pre-reset credential is the old password. For **refresh**, it
is a refresh token belonging to a session the reset is about to revoke.

Both are serialised against the reset by the same mechanism: a
`SELECT ... FOR UPDATE` on the `users` row, taken *before* anything is decided.
The lock order is `users` then `sessions` everywhere, which is why refresh had
to be restructured - VS-003 locked the session row first and never touched the
user row, and adding a user lock after it would have closed a deadlock cycle
against the reset's user-then-sessions order.

Synchronisation is deterministic, not `asyncio.gather` and hope: the racers are
released from a barrier placed immediately after the contended read, which is
the shape VS-005 arrived at after two earlier versions passed against code with
no lock at all.
"""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.confirm_password_reset import ConfirmPasswordReset
from app.identity.application.commands.login import Login
from app.identity.application.commands.refresh_session import RefreshResult, RefreshSession
from app.identity.application.security.password_hasher import hash_password
from app.identity.application.security.session_tokens import (
    decode_access_token,
    issue_refresh_token,
)
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.application.services.admin_mfa_gate import AdminMfaGate
from app.identity.application.services.login_throttle import LoginThrottle
from app.identity.domain.entities import Session
from app.identity.domain.exceptions import (
    InvalidCredentialsError,
    InvalidSessionError,
    SessionTerminatedError,
)
from app.identity.infrastructure.models import SessionModel, UserModel
from app.identity.infrastructure.repositories import (
    MfaCredentialRepository,
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter as AuditWriter

OLD_PASSWORD = "the-password-the-attacker-stole"
NEW_PASSWORD = "the-password-the-reset-installs"

_SYNC_TIMEOUT_SECONDS = 1.0


class _NullThrottle(LoginThrottle):
    """Login's Redis throttle, neutralised.

    These tests are about a database row lock; the throttle would otherwise
    require a Redis container for no reason, and its counters are not part of
    the invariant under test.
    """

    def __init__(self) -> None:
        pass

    async def check(self, *, email: str, ip: str | None) -> None:
        return None

    async def record_failure(self, *, email: str, ip: str | None) -> None:
        return None

    async def reset(self, *, email: str, ip: str | None) -> None:
        return None


class _SyncedUserRepository(UserRepository):
    """Releases every racer at the point immediately after the contended user
    read, so both are inside the read -> decide -> write window together.

    The timeout is what makes that safe in both directions. Unlocked, both
    racers complete their read, both reach the barrier, both proceed from stale
    state and the assertions fail as they must. Locked, the second racer is
    still blocked inside PostgreSQL and never arrives; the first waits, times
    out, commits, and the second then reads the row as the first one left it.
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
        """Overridden too, and not for symmetry: if only the locking readers
        paused here, swapping either command back to an unlocked read - exactly
        the regression this file guards - would bypass the sync point entirely
        and the test would pass against the broken code."""
        return await self._sync(await super().get_by_id(user_id))

    async def get_by_email(self, email: str):  # type: ignore[no-untyped-def]
        return await self._sync(await super().get_by_email(email))


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    """A verified account with a live password reset token outstanding."""
    raw_token = generate_raw_token()
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password(OLD_PASSWORD),
        )
        model = await db.get(UserModel, user.id)
        assert model is not None
        model.email_verified_at = datetime.now(UTC)
        await PasswordResetTokenRepository(db).add(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    return user.id, raw_token


async def _reset(
    session_factory: async_sessionmaker[AsyncSession],
    raw_token: str,
    barrier: asyncio.Barrier,
    revoked: asyncio.Event | None = None,
) -> None:
    async with session_factory() as db, db.begin():
        sessions = (
            SessionRepository(db) if revoked is None else _AnnouncingSessionRepository(db, revoked)
        )
        await ConfirmPasswordReset(
            user_repo=_SyncedUserRepository(db, barrier),
            token_repo=PasswordResetTokenRepository(db),
            session_repo=sessions,
            audit_writer=AuditWriter(db),
        ).execute(
            raw_token=raw_token,
            new_password=NEW_PASSWORD,
            request_id=None,
            ip_hash=None,
        )


class _LateLockingUserRepository(UserRepository):
    """Holds login at the exact point the new algorithm is built around: after
    Argon2 has verified the old hash, and before the row lock is taken.

    That window is the whole reason the lock moved. Argon2 costs ~80ms, and
    holding a `users` lock across it on a public endpoint would let anyone who
    knows an address serialise every operation on that account by guessing. With
    the lock taken afterwards instead, a password reset can commit *inside* the
    window - so login has to re-check, under the lock, that the credential it
    authenticated is still the one stored.

    Waiting on an event rather than a barrier because the ordering here is not
    symmetric: the reset must be allowed to run to completion, and login must
    not reach the lock until it has. A barrier would release both at once and
    the interleaving would be back to chance.
    """

    def __init__(self, session: AsyncSession, reset_committed: asyncio.Event) -> None:
        super().__init__(session)
        self._reset_committed = reset_committed

    async def get_by_id_for_update(self, user_id: uuid.UUID):  # type: ignore[no-untyped-def]
        with suppress(TimeoutError):
            await asyncio.wait_for(self._reset_committed.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return await super().get_by_id_for_update(user_id)


async def _login_after(
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
    password: str,
    reset_committed: asyncio.Event,
) -> object:
    """One login whose row lock is deferred until `reset_committed` fires."""
    async with session_factory() as db, db.begin():
        return await Login(
            user_repo=_LateLockingUserRepository(db, reset_committed),
            session_repo=SessionRepository(db),
            audit_writer=AuditWriter(db),
            throttle=_NullThrottle(),
            mfa_gate=AdminMfaGate(MfaCredentialRepository(db)),
        ).execute(
            email=email,
            password=password,
            ip=None,
            ip_hash=None,
            user_agent=None,
            request_id=None,
        )


async def _login(
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
    password: str,
    barrier: asyncio.Barrier,
) -> object:
    async with session_factory() as db, db.begin():
        return await Login(
            user_repo=_SyncedUserRepository(db, barrier),
            session_repo=SessionRepository(db),
            audit_writer=AuditWriter(db),
            throttle=_NullThrottle(),
            mfa_gate=AdminMfaGate(MfaCredentialRepository(db)),
        ).execute(
            email=email,
            password=password,
            ip=None,
            ip_hash=None,
            user_agent=None,
            request_id=None,
        )


async def _live_sessions(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> int:
    async with session_factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        )
    return int(count or 0)


# --------------------------------------------------------------------------
# Reset vs. ordinary password login
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_login_with_the_old_password_cannot_outlive_the_reset(
    db_engine: AsyncEngine,
) -> None:
    """The attacker knows the stolen password and is signing in at the exact
    moment the real owner completes a reset.

    The dangerous shape is a login that verified the *old* hash and then
    inserted its session after the reset had already run: that session would
    never be revoked, and - because login reads `auth_epoch` from the row it
    locks - its access token would be stamped with the *post-reset* epoch, so it
    would sail straight past every revocation check the reset had just armed.

    The ordering is forced rather than hoped for. Login verifies the old hash,
    then waits; the reset runs to completion and commits; only then does login
    reach `SELECT ... FOR UPDATE`. Under the lock it compares the stored hash
    against the exact one it authenticated, finds it changed, and refuses with
    the ordinary invalid-credentials answer.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed(session_factory)

    async with session_factory() as db:
        user = await UserRepository(db).get_by_id(user_id)
    assert user is not None

    reset_committed = asyncio.Event()

    async def _reset_then_announce() -> None:
        # The event fires only after the transaction context has exited, so it
        # means "committed and visible", not "about to commit".
        await _reset(session_factory, raw_token, asyncio.Barrier(1))
        reset_committed.set()

    reset_outcome, login_outcome = await asyncio.gather(
        _reset_then_announce(),
        _login_after(session_factory, user.email, OLD_PASSWORD, reset_committed),
        return_exceptions=True,
    )

    assert not isinstance(reset_outcome, BaseException), reset_outcome
    # The sequence the algorithm is built for actually happened: login verified
    # the old hash, the reset committed, and only then did login reach the lock.
    assert reset_committed.is_set()

    async with session_factory() as db:
        after = await UserRepository(db).get_by_id(user_id)
    assert after is not None
    assert after.auth_epoch == 1

    # The public answer is the ordinary one - no distinct "password changed
    # mid-login" error, which would confirm both that the address exists and
    # that it was being reset at that moment.
    assert isinstance(login_outcome, InvalidCredentialsError), login_outcome

    assert await _live_sessions(session_factory, user_id) == 0, (
        "a session was created from the pre-reset password after the reset committed "
        f"(login outcome: {login_outcome!r})"
    )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_reset_wins_and_the_old_password_is_refused(
    db_engine: AsyncEngine,
) -> None:
    """The sequential half, stated separately.

    The test above accepts either ordering by design, so on its own it would
    still pass if login simply never worked. Here the reset has fully committed
    first, so there is exactly one correct answer: the old password is dead and
    the new one works.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed(session_factory)
    async with session_factory() as db:
        user = await UserRepository(db).get_by_id(user_id)
    assert user is not None

    await _reset(session_factory, raw_token, asyncio.Barrier(1))

    with pytest.raises(InvalidCredentialsError):
        await _login(session_factory, user.email, OLD_PASSWORD, asyncio.Barrier(1))

    result = await _login(session_factory, user.email, NEW_PASSWORD, asyncio.Barrier(1))

    assert hasattr(result, "access_token")
    assert decode_access_token(result.access_token).auth_epoch == 1


# --------------------------------------------------------------------------
# Reset vs. refresh rotation
# --------------------------------------------------------------------------


async def _seed_session(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> str:
    """One live session, and the raw refresh token that rotates it."""
    session_id = uuid.uuid4()
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=30)
    raw = issue_refresh_token(
        session_id=session_id, token_version=1, expires_at=expires_at, now=now
    )
    async with session_factory() as db, db.begin():
        await SessionRepository(db).add(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_token(raw),
            expires_at=expires_at,
            ip_hash=None,
            user_agent=None,
        )
    return raw


class _LateSavingSessionRepository(SessionRepository):
    """Forces refresh to write its rotated session *after* the reset's
    revocation UPDATE has run.

    This is what makes the refresh test mean something, and it took a second
    attempt to get right. Aligning the two reads on a barrier is not enough:
    after the barrier the reset spends ~80ms inside Argon2 before it revokes,
    while refresh reaches its write almost immediately, so refresh always
    committed first and the revocation always swept up its rotated session. The
    test passed against code with no locks at all.

    Delaying the write inverts that, and exposes the actual hazard. `save()`
    writes `revoked_at` from the in-memory entity, which was read *before* the
    revocation - so a refresh that writes after the sweep does not merely
    survive it, it silently **un-revokes** the session by overwriting
    `revoked_at` back to NULL.

    - **Unlocked:** refresh reads a live session, waits, the reset revokes and
      commits, refresh then writes its stale `revoked_at = None` over the top.
      A session the reset believed it had killed is live again.
    - **Locked:** refresh cannot get past the user row until the reset commits,
      so the wait times out harmlessly and the re-read under
      `get_for_update(populate_existing=True)` sees the revocation.
    """

    def __init__(self, session: AsyncSession, revoked: asyncio.Event) -> None:
        super().__init__(session)
        self._revoked = revoked

    async def save(self, session: Session) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._revoked.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        await super().save(session)


class _AnnouncingSessionRepository(SessionRepository):
    """The reset's half of that handshake: announce the instant revocation has
    run, so the refresh above can aim its write just after it."""

    def __init__(self, session: AsyncSession, revoked: asyncio.Event) -> None:
        super().__init__(session)
        self._revoked = revoked

    async def revoke_all_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
        count = await super().revoke_all_for_user(user_id=user_id, at=at)
        self._revoked.set()
        return count


async def _refresh(
    session_factory: async_sessionmaker[AsyncSession],
    raw_refresh_token: str,
    barrier: asyncio.Barrier,
    revoked: asyncio.Event | None = None,
) -> RefreshResult:
    async with session_factory() as db, db.begin():
        sessions = (
            SessionRepository(db) if revoked is None else _LateSavingSessionRepository(db, revoked)
        )
        return await RefreshSession(
            user_repo=_SyncedUserRepository(db, barrier),
            session_repo=sessions,
            audit_writer=AuditWriter(db),
        ).execute(raw_refresh_token=raw_refresh_token, request_id=None, ip_hash=None)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_refresh_of_a_pre_reset_session_cannot_outlive_the_reset(
    db_engine: AsyncEngine,
) -> None:
    """A refresh token from before the reset, rotated at the moment it lands.

    Both orderings are permitted; what is not permitted is a usable post-reset
    credential emerging from a pre-reset one. If the reset wins, refresh finds a
    revoked session and fails. If refresh wins, it rotates - but the reset then
    revokes the session it rotated, and the access token it minted carries the
    pre-reset epoch, so it is refused twice over.

    This is also the deadlock test. Refresh needs both the user and session rows;
    the reset takes the user row and then updates session rows. If refresh still
    locked the session first, this would deadlock rather than fail an assertion.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed(session_factory)
    raw_refresh = await _seed_session(session_factory, user_id)

    barrier = asyncio.Barrier(2)
    revoked = asyncio.Event()
    reset_outcome, refresh_outcome = await asyncio.gather(
        _reset(session_factory, raw_token, barrier, revoked),
        _refresh(session_factory, raw_refresh, barrier, revoked),
        return_exceptions=True,
    )

    assert not isinstance(reset_outcome, BaseException), reset_outcome

    async with session_factory() as db:
        after = await UserRepository(db).get_by_id(user_id)
    assert after is not None
    assert after.auth_epoch == 1

    assert await _live_sessions(session_factory, user_id) == 0, (
        "a session rotated from a pre-reset refresh token survived the reset "
        f"(refresh outcome: {refresh_outcome!r})"
    )

    if not isinstance(refresh_outcome, BaseException):
        minted = decode_access_token(refresh_outcome.access_token)
        assert minted.auth_epoch != after.auth_epoch, (
            "a pre-reset refresh token minted an access token at the post-reset epoch"
        )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_reset_wins_and_the_pre_reset_refresh_token_is_refused(
    db_engine: AsyncEngine,
) -> None:
    """Sequential half: the reset has committed, so the refresh token belongs to
    a session that no longer exists as far as authentication is concerned."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed(session_factory)
    raw_refresh = await _seed_session(session_factory, user_id)

    await _reset(session_factory, raw_token, asyncio.Barrier(1))

    with pytest.raises((InvalidSessionError, SessionTerminatedError)):
        await _refresh(session_factory, raw_refresh, asyncio.Barrier(1))

    assert await _live_sessions(session_factory, user_id) == 0
