"""Never-verified account purge (F10).

FR-02, failure behaviour: "Never-verified accounts are purged after the
configured period." database-design.md 5.1 permits a physical purge for this
one case, in deliberate contrast to the anonymise-rather-than-delete rule that
governs verified customers - which is why the "verified account survives" test
below is the important one.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.infrastructure.models import UserModel, VerificationTokenModel
from app.identity.infrastructure.repositories import UserRepository, VerificationTokenRepository
from app.jobs.purge_unverified import purge_unverified_accounts
from app.platform.infrastructure.models import AuditLogModel
from app.platform.infrastructure.repositories import AuditLogRepository


def _unique_email() -> str:
    return f"purge-{uuid.uuid4().hex}@example.com"


async def _make_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    age_days: int,
    verified: bool,
) -> tuple[uuid.UUID, str]:
    email = _unique_email()
    created = datetime.now(UTC) - timedelta(days=age_days)

    async with session_factory() as session, session.begin():
        user = await UserRepository(session).add(email=email, password_hash="not-a-real-hash")
        await VerificationTokenRepository(session).add(
            user_id=user.id,
            token_hash=uuid.uuid4().hex * 2,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        await AuditLogRepository(session).add(
            actor_user_id=user.id,
            action="user.registered",
            entity_type="User",
            entity_id=user.id,
        )
        await session.execute(
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                created_at=created,
                email_verified_at=datetime.now(UTC) if verified else None,
            )
        )
    return user.id, email


@pytest.mark.integration
async def test_expired_never_verified_account_is_purged(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, _ = await _make_user(session_factory, age_days=400, verified=False)

    await purge_unverified_accounts({"session_factory": session_factory})

    async with session_factory() as session:
        assert await session.get(UserModel, user_id) is None


@pytest.mark.integration
async def test_recent_unverified_account_survives(db_engine: AsyncEngine) -> None:
    """Someone who registered an hour ago and has not clicked the link yet must
    not have their account deleted out from under them."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, _ = await _make_user(session_factory, age_days=0, verified=False)

    await purge_unverified_accounts({"session_factory": session_factory})

    async with session_factory() as session:
        assert await session.get(UserModel, user_id) is not None


@pytest.mark.integration
async def test_verified_account_survives_regardless_of_age(db_engine: AsyncEngine) -> None:
    """The filter is email_verified_at IS NULL, so age alone can never reach a
    verified customer. Verified accounts are anonymised through account
    deletion, never physically purged."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, _ = await _make_user(session_factory, age_days=4000, verified=True)

    await purge_unverified_accounts({"session_factory": session_factory})

    async with session_factory() as session:
        assert await session.get(UserModel, user_id) is not None


@pytest.mark.integration
async def test_dependent_rows_are_handled_by_their_own_foreign_keys(
    db_engine: AsyncEngine,
) -> None:
    """verification_tokens is ON DELETE CASCADE so it goes with the user;
    audit_logs is ON DELETE SET NULL so the history survives the account."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id, _ = await _make_user(session_factory, age_days=400, verified=False)

    async with session_factory() as session:
        # The identity is (id, created_at) since audit_logs is partitioned (VS-012a).
        audit_key = (
            await session.execute(
                select(AuditLogModel.id, AuditLogModel.created_at).where(
                    AuditLogModel.actor_user_id == user_id
                )
            )
        ).first()
    assert audit_key is not None

    await purge_unverified_accounts({"session_factory": session_factory})

    async with session_factory() as session:
        tokens = (
            await session.scalars(
                select(VerificationTokenModel).where(VerificationTokenModel.user_id == user_id)
            )
        ).all()
        audit = await session.get(AuditLogModel, tuple(audit_key))

    assert tokens == []
    assert audit is not None
    assert audit.actor_user_id is None
