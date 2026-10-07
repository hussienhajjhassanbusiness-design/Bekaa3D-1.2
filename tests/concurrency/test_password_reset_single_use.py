import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.confirm_password_reset import ConfirmPasswordReset
from app.identity.application.security.password_hasher import verify_password
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.domain.exceptions import InvalidPasswordResetTokenError
from app.identity.infrastructure.models import PasswordResetTokenModel
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter as AuditWriter

# Deliberately neutral names. An earlier version called these WINNING_PASSWORD
# and LOSING_PASSWORD and then asserted that the "winner" was the one in force
# afterwards - which is not something this test is entitled to decide. Which
# request wins is settled by which transaction reaches the token's row lock
# first, and that is genuinely nondeterministic: it is the operating system's
# scheduling, not the test's argument order. The names encode that neither is
# expected to win.
PASSWORD_A = "reset-candidate-alpha"
PASSWORD_B = "reset-candidate-beta"


async def _seed_reset_token(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    raw_token = generate_raw_token()
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com", password_hash="not-a-real-hash"
        )
        await PasswordResetTokenRepository(db).add(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    return user.id, raw_token


async def _confirm_once(
    session_factory: async_sessionmaker[AsyncSession], raw_token: str, new_password: str
) -> tuple[str, BaseException | None]:
    """One request's worth of work, transaction boundary included - the same
    shape get_session gives the real route.

    Returns the password it submitted alongside its outcome, so the caller can
    tell *which* attempt won rather than having to assume. `asyncio.gather`
    preserves argument order, but the order in which two racing transactions
    acquire a row lock has nothing to do with the order they were passed in, so
    identity has to travel with the result.
    """
    try:
        async with session_factory() as db, db.begin():
            use_case = ConfirmPasswordReset(
                user_repo=UserRepository(db),
                token_repo=PasswordResetTokenRepository(db),
                session_repo=SessionRepository(db),
                audit_writer=AuditWriter(db),
            )
            await use_case.execute(
                raw_token=raw_token, new_password=new_password, request_id=None, ip_hash=None
            )
    except Exception as exc:
        return new_password, exc
    return new_password, None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_one_reset_token_submitted_twice_at_once_is_redeemed_once(
    db_engine: AsyncEngine,
) -> None:
    """Single-use has to hold under concurrency, not just in sequence.

    Without SELECT ... FOR UPDATE in get_by_hash_for_update, both transactions
    would read the same unused row, both would pass the `used_at IS NULL` check,
    and both would write a password - so whichever committed last would decide
    the account's credential. An attacker racing the real user for a token they
    both hold would win roughly half the time.

    What this test asserts is the *invariant*, not the schedule: exactly one
    attempt succeeds, exactly one is rejected as an invalid token, the stored
    credential is the successful attempt's password, and the token is spent
    once. Either attempt may be the winner and both outcomes are correct.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, raw_token = await _seed_reset_token(session_factory)

    outcomes = await asyncio.gather(
        _confirm_once(session_factory, raw_token, PASSWORD_A),
        _confirm_once(session_factory, raw_token, PASSWORD_B),
    )

    succeeded = [password for password, error in outcomes if error is None]
    rejected = [(password, error) for password, error in outcomes if error is not None]

    assert len(succeeded) == 1, outcomes
    assert len(rejected) == 1, outcomes
    # The loser must fail *for the right reason*. Any other exception would mean
    # the second request crashed rather than being correctly refused, which is a
    # different bug wearing the same shape.
    assert isinstance(rejected[0][1], InvalidPasswordResetTokenError), outcomes

    successful_password = succeeded[0]
    rejected_password = rejected[0][0]
    # Both attempts are accounted for, so a result that silently dropped one
    # cannot pass the checks below by coincidence.
    assert {successful_password, rejected_password} == {PASSWORD_A, PASSWORD_B}

    async with session_factory() as db:
        user = await UserRepository(db).get_by_id(user_id)
        rows = list(
            await db.scalars(
                select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user_id)
            )
        )

    assert user is not None
    # The credential in force belongs to the attempt that actually succeeded -
    # derived from the outcomes, never assumed from argument order.
    assert verify_password(password=successful_password, password_hash=user.password_hash)
    assert not verify_password(password=rejected_password, password_hash=user.password_hash)
    assert len(rows) == 1
    assert rows[0].used_at is not None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_resets_for_different_accounts_do_not_block_each_other(
    db_engine: AsyncEngine,
) -> None:
    """The lock must be per-token. If it serialised all resets, unrelated users
    would queue behind each other."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    _, first_token = await _seed_reset_token(session_factory)
    _, second_token = await _seed_reset_token(session_factory)

    outcomes = await asyncio.gather(
        _confirm_once(session_factory, first_token, PASSWORD_A),
        _confirm_once(session_factory, second_token, PASSWORD_B),
    )

    assert [error for _, error in outcomes if error is not None] == [], outcomes
