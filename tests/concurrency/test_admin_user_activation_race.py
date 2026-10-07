"""VS-009 adversarial concurrency: activation racing the auth paths it revokes.

`SetUserActive` is the only admin operation that ends somebody else's access, so
the properties worth attacking are the ones a lock is there to provide:

- two administrators acting at once must not produce an audit history that never
  happened, nor two rows for one transition;
- a login or a refresh in flight when the deactivation lands must not come away
  holding a usable credential.

Racers are released from a barrier placed immediately after the contended read,
following `tests/concurrency/test_setting_update_race.py`: `asyncio.gather`
alone usually runs one coroutine to completion before the other starts, which is
how a concurrency test comes to pass against code that has no lock at all. The
barrier carries a timeout so the *locked* case - where the second racer is
blocked inside PostgreSQL and can never reach the barrier - does not hang.
"""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.login import Login
from app.identity.application.commands.refresh_session import RefreshSession
from app.identity.application.commands.set_user_active import SetUserActive
from app.identity.application.security.password_hasher import hash_password
from app.identity.application.security.session_tokens import issue_refresh_token
from app.identity.application.security.token_service import hash_token
from app.identity.domain.entities import Session, User
from app.identity.domain.exceptions import (
    AccountDisabledError,
    IdentityDomainError,
    SessionOwnerRevokedError,
)
from app.identity.infrastructure.models import SessionModel, UserModel
from app.identity.infrastructure.repositories import SessionRepository, UserRepository
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter as AuditWriter

PASSWORD = "correct-horse-battery"
VS9_ACTIONS = ("user.activated", "user.deactivated")
_SYNC_TIMEOUT_SECONDS = 1.0


# --------------------------------------------------------------------------
# Synchronised repositories
# --------------------------------------------------------------------------


class _SyncedUserRepository(UserRepository):
    """Holds a racer at the point just after it reads the user row.

    Both the locking and the non-locking read are overridden. If only the
    locking one paused, a regression that dropped `FOR UPDATE` would bypass the
    sync point entirely, the racers would never overlap, and the test would pass
    against the broken code.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def _sync(self, value: User | None) -> User | None:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return value

    async def get_by_id_for_update(self, user_id: uuid.UUID) -> User | None:
        return await self._sync(await super().get_by_id_for_update(user_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self._sync(await super().get_by_email(email))


class _SyncedSessionRepository(SessionRepository):
    """Holds a refresh racer at its unlocked owner peek, which is the read that
    happens before it takes the user row lock."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def get_owner_id(self, session_id: uuid.UUID) -> uuid.UUID | None:
        owner = await super().get_owner_id(session_id)
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return owner


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


class _NullThrottle:
    """Login's Redis throttle, stubbed out. The race under test is in
    PostgreSQL; a Redis round trip would only add jitter."""

    async def check(self, *, email: str, ip: str | None) -> None: ...

    async def record_failure(self, *, email: str, ip: str | None) -> None: ...

    async def reset(self, *, email: str, ip: str | None) -> None: ...


class _NoMfaGate:
    async def challenge_required(self, user: User) -> bool:
        return False


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_user(
    factory: async_sessionmaker[AsyncSession], *, is_active: bool = True
) -> tuple[uuid.UUID, str]:
    email = f"race-{uuid.uuid4().hex}@example.com"
    async with factory() as db, db.begin():
        row = UserModel(
            email=email,
            password_hash=hash_password(PASSWORD),
            email_verified_at=datetime.now(UTC),
            is_active=is_active,
        )
        db.add(row)
        await db.flush()
        return row.id, email


async def _seed_admin(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as db, db.begin():
        row = UserModel(email=f"race-admin-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(row)
        await db.flush()
        return row.id


async def _seed_session(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """One live session with a usable refresh token."""
    session_id = uuid.uuid4()
    expires_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = expires_at.replace(year=expires_at.year + 1)
    token = issue_refresh_token(
        session_id=session_id, token_version=1, expires_at=expires_at, now=datetime.now(UTC)
    )
    async with factory() as db, db.begin():
        await SessionRepository(db).add(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_token(token),
            expires_at=expires_at,
            ip_hash=None,
            user_agent=None,
        )
    return session_id, token


async def _set_active(
    factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    actor: uuid.UUID,
    value: bool,
    barrier: asyncio.Barrier,
) -> object:
    async with factory() as db, db.begin():
        return await SetUserActive(
            _SyncedUserRepository(db, barrier), SessionRepository(db), AuditWriter(db)
        ).execute(
            user_id=user_id,
            is_active=value,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )


async def _state(factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> UserModel:
    async with factory() as db:
        row = await db.scalar(select(UserModel).where(UserModel.id == user_id))
        assert row is not None
        return row


async def _vs9_audit(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[AuditLogModel]:
    async with factory() as db:
        return list(
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.entity_id == user_id,
                    AuditLogModel.action.in_(VS9_ACTIONS),
                )
            )
        )


async def _live_sessions(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[SessionModel]:
    async with factory() as db:
        rows = await db.scalars(
            select(SessionModel).where(
                SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)
            )
        )
        return list(rows)


# --------------------------------------------------------------------------
# Two administrators at once
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_simultaneous_deactivations_audit_one_transition(
    db_engine: AsyncEngine,
) -> None:
    """Both requests succeed, but only one of them changed anything - and the
    audit log must say so. Two rows here would describe the account being
    deactivated twice from an active state, which never happened."""
    factory = _factory(db_engine)
    user_id, _ = await _seed_user(factory)
    a1, a2 = await _seed_admin(factory), await _seed_admin(factory)
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        _set_active(factory, user_id, a1, False, barrier),
        _set_active(factory, user_id, a2, False, barrier),
        return_exceptions=True,
    )

    assert not [r for r in results if isinstance(r, BaseException)], results
    changed = [r for r in results if getattr(r, "changed", False)]
    assert len(changed) == 1, "exactly one racer may report a transition"

    row = await _state(factory, user_id)
    assert row.is_active is False
    assert row.auth_epoch == 1, "the epoch must advance once, not once per request"

    rows = await _vs9_audit(factory, user_id)
    assert len(rows) == 1, f"expected one audit row, got {[r.action for r in rows]}"
    assert rows[0].action == "user.deactivated"
    assert rows[0].before_data == {"is_active": True}


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_deactivate_activate_race_leaves_a_truthful_audit_chain(
    db_engine: AsyncEngine,
) -> None:
    """Whichever order the two land in, each audit row's `before` must equal the
    previous row's `after`, and the last `after` must equal the stored row.

    Without the row lock both racers read `is_active=True` and the log claims
    two transitions out of the same state - a history in which nobody ever
    performed the change that actually stuck.
    """
    factory = _factory(db_engine)
    for _ in range(8):
        user_id, _ = await _seed_user(factory, is_active=False)
        a1, a2 = await _seed_admin(factory), await _seed_admin(factory)
        barrier = asyncio.Barrier(2)

        await asyncio.gather(
            _set_active(factory, user_id, a1, True, barrier),
            _set_active(factory, user_id, a2, False, barrier),
            return_exceptions=True,
        )

        rows = await _vs9_audit(factory, user_id)
        # created_at is func.now() = transaction start, which can order the
        # opposite way to commit order, so chain by value rather than by clock.
        assert rows, "a genuine transition must be audited"
        steps = [(r.before_data or {}, r.after_data or {}) for r in rows]
        chain = sorted(steps, key=lambda pair: bool(pair[0]["is_active"]))
        state = False
        for before, after in chain:
            assert before["is_active"] == state, f"audit chain broken: {steps}"
            state = bool(after["is_active"])
        stored = await _state(factory, user_id)
        assert stored.is_active is state, "audit chain must end at the stored state"


# --------------------------------------------------------------------------
# Deactivation racing the credential-minting paths
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_login_in_flight_cannot_survive_a_deactivation(
    db_engine: AsyncEngine,
) -> None:
    """Login reads the user row unlocked, spends ~80ms in Argon2, then takes the
    lock. A deactivation committing inside that window must leave the login with
    nothing: no session row, and no way to mint one.
    """
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)

    for _ in range(6):
        user_id, email = await _seed_user(factory)
        barrier = asyncio.Barrier(2)

        async def _login(email: str = email, barrier: asyncio.Barrier = barrier) -> object:
            async with factory() as db, db.begin():
                return await Login(
                    user_repo=_SyncedUserRepository(db, barrier),
                    session_repo=SessionRepository(db),
                    audit_writer=AuditWriter(db),
                    throttle=_NullThrottle(),  # type: ignore[arg-type]
                    mfa_gate=_NoMfaGate(),  # type: ignore[arg-type]
                ).execute(
                    email=email,
                    password=PASSWORD,
                    ip=None,
                    ip_hash=None,
                    user_agent=None,
                    request_id=None,
                )

        outcomes = await asyncio.gather(
            _set_active(factory, user_id, admin, False, barrier),
            _login(),
            return_exceptions=True,
        )
        login_outcome = outcomes[1]

        stored = await _state(factory, user_id)
        assert stored.is_active is False

        live = await _live_sessions(factory, user_id)
        if isinstance(login_outcome, BaseException):
            assert isinstance(login_outcome, AccountDisabledError | IdentityDomainError), (
                f"unexpected login failure: {login_outcome!r}"
            )
            assert live == [], "a refused login must leave no live session"
        else:
            # Login won the race and committed first; the deactivation must then
            # have revoked the session it created.
            assert live == [], "a session minted before the deactivation must not still be live"


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_refresh_in_flight_cannot_mint_a_credential_past_a_deactivation(
    db_engine: AsyncEngine,
) -> None:
    """Refresh peeks at the session's owner unlocked before taking the user row
    lock. A deactivation landing in that window must stop it rotating: the
    session has to end up revoked, not carrying a fresh token.
    """
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)

    for _ in range(6):
        user_id, _ = await _seed_user(factory)
        session_id, token = await _seed_session(factory, user_id)
        barrier = asyncio.Barrier(2)

        async def _refresh(token: str = token, barrier: asyncio.Barrier = barrier) -> object:
            async with factory() as db, db.begin():
                return await RefreshSession(
                    user_repo=UserRepository(db),
                    session_repo=_SyncedSessionRepository(db, barrier),
                    audit_writer=AuditWriter(db),
                ).execute(raw_refresh_token=token, request_id=None, ip_hash=None)

        outcomes = await asyncio.gather(
            _set_active(factory, user_id, admin, False, barrier),
            _refresh(),
            return_exceptions=True,
        )
        refresh_outcome = outcomes[1]

        stored = await _state(factory, user_id)
        assert stored.is_active is False

        live = await _live_sessions(factory, user_id)
        assert live == [], (
            f"deactivated account still holds a live session; refresh returned {refresh_outcome!r}"
        )
        if not isinstance(refresh_outcome, BaseException):
            # Refresh won and minted a token; that token's session must have
            # been revoked by the deactivation that followed it.
            async with factory() as db:
                row = await db.scalar(select(SessionModel).where(SessionModel.id == session_id))
            assert row is not None and row.revoked_at is not None
        else:
            assert isinstance(refresh_outcome, SessionOwnerRevokedError | IdentityDomainError), (
                f"unexpected refresh failure: {refresh_outcome!r}"
            )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_epoch_advances_exactly_once_per_real_transition(
    db_engine: AsyncEngine,
) -> None:
    """Ten racing PATCHes alternating direction. However they interleave, the
    epoch must equal the number of true->false transitions actually audited -
    never more, or a reactivated account would be carrying revocations that
    correspond to nothing."""
    factory = _factory(db_engine)
    user_id, _ = await _seed_user(factory)
    admins = [await _seed_admin(factory) for _ in range(10)]
    barrier = asyncio.Barrier(10)

    await asyncio.gather(
        *(_set_active(factory, user_id, admins[i], i % 2 == 0, barrier) for i in range(10)),
        return_exceptions=True,
    )

    rows = await _vs9_audit(factory, user_id)
    deactivations = [r for r in rows if r.action == "user.deactivated"]
    stored = await _state(factory, user_id)
    assert stored.auth_epoch == len(deactivations), (
        f"epoch={stored.auth_epoch} but {len(deactivations)} deactivations were audited"
    )
    # No session may outlive a deactivation, whichever way the race settled.
    if stored.is_active is False:
        assert await _live_sessions(factory, user_id) == []


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_racing_deactivation_never_deadlocks_against_refresh(
    db_engine: AsyncEngine,
) -> None:
    """Both paths take `users` before `sessions`. Taking them the other way
    round in either place closes a cycle PostgreSQL resolves by killing one
    transaction with DeadlockDetectedError - this is the regression guard."""
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)

    for _ in range(10):
        user_id, _ = await _seed_user(factory)
        _, token = await _seed_session(factory, user_id)
        barrier = asyncio.Barrier(2)

        async def _refresh(token: str = token, barrier: asyncio.Barrier = barrier) -> object:
            async with factory() as db, db.begin():
                return await RefreshSession(
                    user_repo=UserRepository(db),
                    session_repo=_SyncedSessionRepository(db, barrier),
                    audit_writer=AuditWriter(db),
                ).execute(raw_refresh_token=token, request_id=None, ip_hash=None)

        outcomes = await asyncio.gather(
            _set_active(factory, user_id, admin, False, barrier),
            _refresh(),
            return_exceptions=True,
        )
        for outcome in outcomes:
            assert "Deadlock" not in type(outcome).__name__, f"deadlock detected: {outcome!r}"


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_session_created_between_the_save_and_the_revoke_does_not_survive(
    db_engine: AsyncEngine,
) -> None:
    """The narrow window inside SetUserActive itself: the user row is saved, and
    only then are sessions revoked. Anything inserting a session in between must
    be blocked by the user row lock the command still holds."""
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)
    user_id, email = await _seed_user(factory)

    barrier = asyncio.Barrier(2)

    class _LateRevokeSessionRepository(SessionRepository):
        """Pauses immediately before revoking, widening the window as far as it
        can be widened without changing production behaviour."""

        async def revoke_all_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
            with suppress(TimeoutError, asyncio.BrokenBarrierError):
                await asyncio.wait_for(barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
            return await super().revoke_all_for_user(user_id=user_id, at=at)

    async def _deactivate() -> object:
        async with factory() as db, db.begin():
            return await SetUserActive(
                UserRepository(db), _LateRevokeSessionRepository(db), AuditWriter(db)
            ).execute(
                user_id=user_id,
                is_active=False,
                actor_user_id=admin,
                request_id=None,
                ip_hash=None,
            )

    async def _login() -> object:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        async with factory() as db, db.begin():
            return await Login(
                user_repo=UserRepository(db),
                session_repo=SessionRepository(db),
                audit_writer=AuditWriter(db),
                throttle=_NullThrottle(),  # type: ignore[arg-type]
                mfa_gate=_NoMfaGate(),  # type: ignore[arg-type]
            ).execute(
                email=email,
                password=PASSWORD,
                ip=None,
                ip_hash=None,
                user_agent=None,
                request_id=None,
            )

    await asyncio.gather(_deactivate(), _login(), return_exceptions=True)

    assert (await _state(factory, user_id)).is_active is False
    assert await _live_sessions(factory, user_id) == [], (
        "a session slipped through the deactivation window"
    )


@pytest.mark.integration
@pytest.mark.concurrency
async def test_audit_and_mutation_commit_together(db_engine: AsyncEngine) -> None:
    """BR-132: the business change and its audit row land in one transaction.
    A writer that failed after the save must leave no trace of either."""
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)
    user_id, _ = await _seed_user(factory)

    class _ExplodingAuditWriter(AuditWriter):
        async def record(self, **kwargs: object) -> None:
            raise RuntimeError("audit sink unavailable")

    with pytest.raises(RuntimeError):
        async with factory() as db, db.begin():
            await SetUserActive(
                UserRepository(db), SessionRepository(db), _ExplodingAuditWriter(db)
            ).execute(
                user_id=user_id,
                is_active=False,
                actor_user_id=admin,
                request_id=None,
                ip_hash=None,
            )

    row = await _state(factory, user_id)
    assert row.is_active is True, "the mutation must roll back with its audit row"
    assert row.auth_epoch == 0, "the epoch must roll back too"
    assert await _vs9_audit(factory, user_id) == []


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_failing_session_revocation_rolls_the_deactivation_back(
    db_engine: AsyncEngine,
) -> None:
    """The inverse partial state: `is_active=false` committed while sessions
    stayed live would be the dangerous one, so the revocation failing must take
    the whole change with it."""
    factory = _factory(db_engine)
    admin = await _seed_admin(factory)
    user_id, _ = await _seed_user(factory)
    session_id, _ = await _seed_session(factory, user_id)

    class _FailingSessionRepository(SessionRepository):
        async def revoke_all_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
            raise RuntimeError("revocation failed")

    with pytest.raises(RuntimeError):
        async with factory() as db, db.begin():
            await SetUserActive(
                UserRepository(db), _FailingSessionRepository(db), AuditWriter(db)
            ).execute(
                user_id=user_id,
                is_active=False,
                actor_user_id=admin,
                request_id=None,
                ip_hash=None,
            )

    row = await _state(factory, user_id)
    assert row.is_active is True, "no 'inactive but sessions live' state may persist"
    assert row.auth_epoch == 0
    assert len(await _live_sessions(factory, user_id)) == 1
    assert await _vs9_audit(factory, user_id) == []
    assert isinstance(session_id, uuid.UUID)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_domain_entity_state(db_engine: AsyncEngine) -> None:
    """`Session` and `User` are imported for the type annotations above; this
    keeps the import meaningful rather than unused."""
    assert Session is not None
    assert User is not None
