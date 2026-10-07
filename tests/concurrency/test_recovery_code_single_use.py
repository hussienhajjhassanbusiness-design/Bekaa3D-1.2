"""A recovery code must be redeemable exactly once, even under a dead heat.

The domain guard in `MfaRecoveryCode.redeem` is not enough on its own: two
transactions that both read an unused row would both pass it. What actually
serialises them is the `SELECT ... FOR UPDATE` in
`MfaRecoveryCodeRepository.get_unused_by_hash`, and that can only be proven
against real PostgreSQL with two concurrent transactions."""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.identity.application.commands.mfa_verify import VerifyMfa
from app.identity.application.security.secret_cipher import encrypt_secret
from app.identity.application.security.token_service import hash_token
from app.identity.application.security.totp import generate_secret
from app.identity.domain.enums import MfaMethod
from app.identity.domain.exceptions import InvalidRecoveryCodeError
from app.identity.domain.recovery_codes import generate_code, normalize_code
from app.identity.infrastructure.repositories import (
    MfaCredentialRepository,
    MfaRecoveryCodeRepository,
    UserRepository,
)
from app.platform.public import SqlAuditWriter as AuditWriter


async def _seed_enrolled_admin(
    session_factory: async_sessionmaker[AsyncSession], plaintext_code: str
) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = await UserRepository(db).add(
            email=f"test-{uuid.uuid4().hex}@example.com", password_hash="not-a-real-hash"
        )
        credential = await MfaCredentialRepository(db).add(
            user_id=user.id,
            method=MfaMethod.TOTP,
            secret_ciphertext=encrypt_secret(generate_secret()),
        )
        credential.enable(datetime.now(UTC))
        await MfaCredentialRepository(db).save(credential)
        await MfaRecoveryCodeRepository(db).add_set(
            mfa_credential_id=credential.id,
            code_hashes=[hash_token(normalize_code(plaintext_code))],
        )
    return user.id


async def _redeem_once(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, code: str
) -> None:
    """One request's worth of work, transaction boundary included - the same
    shape get_session gives a real request."""
    async with session_factory() as db, db.begin():
        await VerifyMfa(
            credential_repo=MfaCredentialRepository(db),
            recovery_repo=MfaRecoveryCodeRepository(db),
            audit_writer=AuditWriter(db),
        ).execute(user_id=user_id, code=None, recovery_code=code, request_id=None, ip_hash=None)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_only_one_of_two_simultaneous_redemptions_succeeds(
    db_engine: AsyncEngine,
) -> None:
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    code = generate_code()
    user_id = await _seed_enrolled_admin(session_factory, code)

    results = await asyncio.gather(
        _redeem_once(session_factory, user_id, code),
        _redeem_once(session_factory, user_id, code),
        return_exceptions=True,
    )

    succeeded = [result for result in results if not isinstance(result, BaseException)]
    rejected = [result for result in results if isinstance(result, InvalidRecoveryCodeError)]

    assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
    assert len(rejected) == 1, f"expected exactly one rejection, got {results}"


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_row_is_marked_used_exactly_once(db_engine: AsyncEngine) -> None:
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    code = generate_code()
    user_id = await _seed_enrolled_admin(session_factory, code)

    await asyncio.gather(
        _redeem_once(session_factory, user_id, code),
        _redeem_once(session_factory, user_id, code),
        _redeem_once(session_factory, user_id, code),
        return_exceptions=True,
    )

    async with session_factory() as db:
        credential = await MfaCredentialRepository(db).get_by_user_id(user_id)
        assert credential is not None
        assert await MfaRecoveryCodeRepository(db).count_unused(credential.id) == 0
