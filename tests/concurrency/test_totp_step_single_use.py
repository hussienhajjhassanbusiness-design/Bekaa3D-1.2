"""A TOTP time-step must be spendable exactly once, even under a dead heat.

`MfaCredential.record_totp_step` uses `max()`, but that only orders values
already inside one process's memory. Two transactions that both read the same
stale `last_totp_step` would both conclude the step was unspent and both accept
the code - one intercepted OTP, two admin sessions. What actually serialises
them is the `SELECT ... FOR UPDATE` in
`MfaCredentialRepository.get_by_user_id_for_update`, and that can only be
proven against real PostgreSQL with two concurrent transactions.

Each coroutine below opens its own session and its own transaction, which is
the same shape `get_session` gives a real request - two independent MFA
challenges arriving at the same instant.
"""

import asyncio
import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime

import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.identity.application.commands.mfa_verify import VerifyMfa
from app.identity.application.security.secret_cipher import encrypt_secret
from app.identity.application.security.totp import TOTP_STEP_SECONDS, current_step, generate_secret
from app.identity.domain.entities import MfaCredential
from app.identity.domain.enums import MfaMethod
from app.identity.domain.exceptions import InvalidMfaCodeError
from app.identity.infrastructure.repositories import (
    MfaCredentialRepository,
    MfaRecoveryCodeRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter as AuditWriter

# Long enough that a genuinely concurrent racer arrives, short enough that the
# locked case - where the second racer cannot arrive - does not drag the suite.
_SYNC_TIMEOUT_SECONDS = 1.0


async def _seed_enrolled_admin(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    """An administrator with MFA enabled and no TOTP step spent yet."""
    secret = generate_secret()
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com", password_hash="not-a-real-hash"
        )
        credential = await MfaCredentialRepository(db).add(
            user_id=user.id, method=MfaMethod.TOTP, secret_ciphertext=encrypt_secret(secret)
        )
        credential.enable(datetime.now(UTC))
        await MfaCredentialRepository(db).save(credential)
    return user.id, secret


class _SyncedCredentialRepository(MfaCredentialRepository):
    """Holds every racer at the point between reading the credential and
    writing the new mark.

    This is the instrument the test needs, and it is worth being precise about
    why. The window being tested is exactly read -> decide -> write; a race
    only demonstrates anything if both transactions are inside it at once.
    Bare `asyncio.gather` does not achieve that - the coroutines usually run one
    to completion before the other starts - and neither does a barrier placed
    *before* the read, because `asyncio.Barrier` lets the last arriver continue
    without yielding, so it can finish its whole transaction first. Either way
    the test passes against unlocked code, which makes it decorative.

    So the sync point goes immediately after the read. The timeout is what
    makes that safe in both directions:

    - **Unlocked:** both racers complete their read, both reach the barrier,
      both are released, and both then write from stale data. The race is real
      and the test fails, as it must.
    - **Locked:** the second racer is still blocked inside PostgreSQL on
      `SELECT ... FOR UPDATE` and never arrives. The first waits, times out,
      proceeds, and commits; the lock releases; the second finally reads the
      advanced row and correctly refuses the code.

    Without the timeout the locked case would deadlock on a barrier that can
    never fill."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def _sync(self, credential: MfaCredential | None) -> MfaCredential | None:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._barrier.wait(), timeout=_SYNC_TIMEOUT_SECONDS)
        return credential

    async def get_by_user_id_for_update(self, user_id: uuid.UUID) -> MfaCredential | None:
        return await self._sync(await super().get_by_user_id_for_update(user_id))

    async def get_by_user_id(self, user_id: uuid.UUID) -> MfaCredential | None:
        """Overridden as well, and not for symmetry.

        If only the locking reader paused here, then swapping the command back
        to the plain read - precisely the regression this file exists to catch -
        would bypass the sync point entirely, the racers would never overlap,
        and the test would go green against the broken code. The instrument has
        to survive the break it is testing for."""
        return await self._sync(await super().get_by_user_id(user_id))


async def _verify_holding_the_window_open(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    code: str,
    barrier: asyncio.Barrier,
) -> None:
    """One request, paused between reading the credential and writing the mark."""
    async with session_factory() as db, db.begin():
        await VerifyMfa(
            credential_repo=_SyncedCredentialRepository(db, barrier),
            recovery_repo=MfaRecoveryCodeRepository(db),
            audit_writer=AuditWriter(db),
        ).execute(user_id=user_id, code=code, recovery_code=None, request_id=None, ip_hash=None)


async def _verify_once(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    code: str,
    barrier: asyncio.Barrier | None = None,
) -> None:
    """One request's worth of work, transaction boundary included.

    `barrier` releases every racer inside an already-open transaction and
    immediately before the credential read, which is what makes the race
    deterministic rather than a matter of luck. Two bare `asyncio.gather`
    coroutines will often run one to completion before the other starts, and a
    concurrency test that only sometimes exercises the window it is named after
    is worse than no test - it passes against the unlocked code too.

    Releasing *before* the read rather than after is deliberate: with the lock
    in place, a racer that reached a barrier after its read would already be
    blocked inside PostgreSQL and never arrive, hanging the test.
    """
    async with session_factory() as db, db.begin():
        if barrier is not None:
            await barrier.wait()
        await VerifyMfa(
            credential_repo=MfaCredentialRepository(db),
            recovery_repo=MfaRecoveryCodeRepository(db),
            audit_writer=AuditWriter(db),
        ).execute(user_id=user_id, code=code, recovery_code=None, request_id=None, ip_hash=None)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_only_one_of_two_simultaneous_verifications_of_one_code_succeeds(
    db_engine: AsyncEngine,
) -> None:
    """Two independent challenges, the same valid TOTP, submitted together.

    Exactly one must complete; the other must be refused with the ordinary
    invalid-code answer, indistinguishable from a wrong code.
    """
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, secret = await _seed_enrolled_admin(session_factory)
    code = pyotp.TOTP(secret).now()

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _verify_holding_the_window_open(session_factory, user_id, code, barrier),
        _verify_holding_the_window_open(session_factory, user_id, code, barrier),
        return_exceptions=True,
    )

    succeeded = [result for result in results if not isinstance(result, BaseException)]
    rejected = [result for result in results if isinstance(result, InvalidMfaCodeError)]

    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    assert len(rejected) == 1, f"expected exactly one rejection, got {results}"


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_step_is_spent_once_however_many_requests_race_for_it(
    db_engine: AsyncEngine,
) -> None:
    """Widened to four racers, and asserted against stored state rather than
    return values: whatever interleaving occurs, the credential must end up
    holding exactly that step."""
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, secret = await _seed_enrolled_admin(session_factory)
    now = datetime.now(UTC)
    code = pyotp.TOTP(secret).now()

    barrier = asyncio.Barrier(4)
    results = await asyncio.gather(
        *(
            _verify_holding_the_window_open(session_factory, user_id, code, barrier)
            for _ in range(4)
        ),
        return_exceptions=True,
    )
    succeeded = [result for result in results if not isinstance(result, BaseException)]

    async with session_factory() as db:
        credential = await MfaCredentialRepository(db).get_by_user_id(user_id)

    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    assert credential is not None
    assert credential.last_totp_step == current_step(now)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_accepted_steps_leave_the_mark_at_the_higher_one(
    db_engine: AsyncEngine,
) -> None:
    """Forward progress under a race.

    Two *different* valid steps are submitted together - the current one and
    the next, both inside the verifier's drift window - so both are legitimate
    codes rather than a replay of one. Whichever order they commit in, the
    stored mark must never be left below the highest step that was accepted; a
    mark that slipped backwards would make an already-spent step redeemable
    again.
    """
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, secret = await _seed_enrolled_admin(session_factory)

    totp = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    this_step = totp.now()
    next_step = totp.at(int(now.timestamp()) + TOTP_STEP_SECONDS)

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _verify_holding_the_window_open(session_factory, user_id, this_step, barrier),
        _verify_holding_the_window_open(session_factory, user_id, next_step, barrier),
        return_exceptions=True,
    )
    accepted = [result for result in results if not isinstance(result, BaseException)]

    async with session_factory() as db:
        credential = await MfaCredentialRepository(db).get_by_user_id(user_id)

    assert credential is not None
    assert credential.last_totp_step is not None
    # If the later code was accepted at all, the mark must be at its step - not
    # dragged back by the earlier one committing second.
    assert credential.last_totp_step >= current_step(now)
    assert len(accepted) >= 1, f"at least one legitimate code must be accepted, got {results}"
    # And whatever was accepted is now spent: replaying either is refused.
    replay = await asyncio.gather(
        _verify_once(session_factory, user_id, this_step),
        _verify_once(session_factory, user_id, next_step),
        return_exceptions=True,
    )
    assert all(isinstance(result, InvalidMfaCodeError) for result in replay), replay
