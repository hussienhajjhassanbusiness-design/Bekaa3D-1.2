"""What a user sees before and after the purge (VS-046, Q3, amendment F).

An expired link answers 410 while its row exists and 400 INVALID_TOKEN once purged."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.infrastructure.models import SessionModel, VerificationTokenModel
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    VerificationTokenRepository,
)
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.jobs.purge_security_records import purge_expired_security_records
from app.main import app as main_app
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    fresh_ip,
    login,
)

NOW = datetime(2000, 3, 1, tzinfo=UTC)
LONG_EXPIRED = datetime(2000, 1, 1, tzinfo=UTC)


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


def _stable(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in ("request_id", "instance")}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_expired_verification_link_turns_from_410_to_400_once_purged(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session, verified=False)
    raw = generate_raw_token()
    async with async_sessionmaker(db_engine)() as s, s.begin():
        await VerificationTokenRepository(s).add(
            user_id=user.id, token_hash=hash_token(raw), expires_at=LONG_EXPIRED
        )
    with client_for(main_app, ip=fresh_ip()) as client:
        assert_problem(client.post("/api/v1/auth/verify-email", json={"token": raw}), 410)
        await purge_expired_security_records(_ctx(db_engine), now=NOW)
        after = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert_problem(after, 400, "INVALID_TOKEN")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_expired_reset_link_turns_from_410_to_400_once_purged(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session)
    raw = generate_raw_token()
    async with async_sessionmaker(db_engine)() as s, s.begin():
        await PasswordResetTokenRepository(s).add(
            user_id=user.id, token_hash=hash_token(raw), expires_at=LONG_EXPIRED
        )
    body = {"token": raw, "new_password": "a-new-password-123"}
    with client_for(main_app, ip=fresh_ip()) as client:
        assert_problem(client.post("/api/v1/auth/password-reset/confirm", json=body), 410)
        await purge_expired_security_records(_ctx(db_engine), now=NOW)
        after = client.post("/api/v1/auth/password-reset/confirm", json=body)
    assert_problem(after, 400, "INVALID_TOKEN")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_revoked_sessions_refresh_answers_identically_before_and_after_the_purge(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session)
    user_id, email = user.id, user.email
    with client_for(main_app, ip=fresh_ip()) as client:
        login(client, email)
        async with db_engine.begin() as conn:
            await conn.execute(
                update(SessionModel)
                .where(SessionModel.user_id == user_id)
                .values(revoked_at=LONG_EXPIRED)
            )
        headers = csrf(client)
        before = client.post("/api/v1/auth/refresh", headers=headers)
        await purge_expired_security_records(_ctx(db_engine), now=NOW)
        async with db_engine.connect() as conn:
            left = await conn.scalar(select(func.count()).where(SessionModel.user_id == user_id))
        after = client.post("/api/v1/auth/refresh", headers=headers)
    assert left == 0
    assert before.status_code == after.status_code == 401
    assert _stable(before.json()) == _stable(after.json())


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_resend_cooldown_is_unaffected(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """The cooldown reads the latest token's created_at; a fresh token is never purgeable."""
    user = await create_user(db_session, verified=False)
    user_id, email = user.id, user.email
    payload = {"email": email, "captcha_token": FAKE_CAPTCHA_PASS}

    async def tokens() -> int:
        async with db_engine.connect() as conn:
            count = await conn.scalar(
                select(func.count()).where(VerificationTokenModel.user_id == user_id)
            )
        return int(count or 0)

    with client_for(main_app, ip=fresh_ip()) as client:
        assert client.post("/api/v1/auth/resend-verification", json=payload).status_code == 202
        assert await tokens() == 1
        await purge_expired_security_records(_ctx(db_engine), now=NOW)
        await purge_expired_security_records(_ctx(db_engine))
        assert await tokens() == 1
        assert client.post("/api/v1/auth/resend-verification", json=payload).status_code == 202
    assert await tokens() == 1  # still inside the cooldown: no second token
