"""BUG-46: every write is committed *before* the response is sent.

FastAPI exits request-scoped yield dependencies after the response has gone
out, so `get_session`'s commit used to run after the client already had its
2xx. A commit that then failed - a deferred constraint, a serialisation
failure, the database dropping the connection - left the client believing a
write had happened that never did.

The commit failure is produced for real, at the database: a deferred
constraint trigger lets matching rows through every statement and rejects them
only at COMMIT. Each test checks both halves - the response must be an error,
and the write must really be absent.
"""

import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.engagement.domain.enums import NotificationType
from app.engagement.infrastructure.models import NotificationModel
from app.engagement.public import create_notification
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.infrastructure.models import SessionModel, UserModel
from app.identity.infrastructure.repositories import PasswordResetTokenRepository
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.main import app as main_app
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
)

MARK = "fail-at-commit"
# Inserted normally, rejected at COMMIT only when later *updated*.
UPDATE_MARK = "fail-on-update"


@pytest.fixture
async def commit_fails_for_marked_rows(db_engine: AsyncEngine) -> AsyncGenerator[None]:
    statements = [
        """
        CREATE OR REPLACE FUNCTION deep_reject_at_commit() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'deep test: this row is rejected at COMMIT';
        END $$
        """,
        f"""
        CREATE CONSTRAINT TRIGGER deep_users_insert_at_commit
        AFTER INSERT ON users DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        WHEN (NEW.email::text LIKE '{MARK}-%')
        EXECUTE FUNCTION deep_reject_at_commit()
        """,
        f"""
        CREATE CONSTRAINT TRIGGER deep_users_update_at_commit
        AFTER UPDATE ON users DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        WHEN (NEW.email::text LIKE '{UPDATE_MARK}-%')
        EXECUTE FUNCTION deep_reject_at_commit()
        """,
        f"""
        CREATE CONSTRAINT TRIGGER deep_notifications_update_at_commit
        AFTER UPDATE ON notifications DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        WHEN (NEW.payload->>'event' = '{MARK}')
        EXECUTE FUNCTION deep_reject_at_commit()
        """,
    ]
    async with db_engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TRIGGER deep_users_insert_at_commit ON users"))
        await conn.execute(text("DROP TRIGGER deep_users_update_at_commit ON users"))
        await conn.execute(
            text("DROP TRIGGER deep_notifications_update_at_commit ON notifications")
        )
        await conn.execute(text("DROP FUNCTION deep_reject_at_commit()"))


def _marked_email() -> str:
    return f"{MARK}-{uuid.uuid4().hex}@example.com"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "commit_fails_for_marked_rows")
async def test_a_registration_whose_commit_fails_is_not_answered_202(
    db_session: AsyncSession,
) -> None:
    email = _marked_email()
    with client_for(main_app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
        )
    db_session.expire_all()
    stored = await db_session.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.email == email)
    )
    assert stored == 0, "the trigger must really have rejected the commit"
    assert_problem(response, 500, "INTERNAL_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "commit_fails_for_marked_rows")
async def test_a_notification_update_whose_commit_fails_is_not_answered_200(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = await create_user(db_session)
    async with AsyncSession(db_engine) as session, session.begin():
        notification = await create_notification(
            session,
            user_id=user.id,
            notification_type=NotificationType.ACCOUNT,
            payload={"event": MARK},
        )
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = client.patch(
            f"/api/v1/me/notifications/{notification.id}",
            json={"read": True},
            headers=csrf(client),
        )
    db_session.expire_all()
    row = await db_session.get(NotificationModel, notification.id)
    assert row is not None and row.read_at is None, "the update must really be absent"
    assert_problem(response, 500, "INTERNAL_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "commit_fails_for_marked_rows")
async def test_a_password_reset_whose_commit_fails_is_not_reported_as_done(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    """The dangerous case: a 204 tells the user their password was changed and
    every other session ended, while in fact neither happened."""
    user = await create_user(db_session, email=f"{UPDATE_MARK}-{uuid.uuid4().hex}@example.com")
    uid, email, old_hash = user.id, user.email, user.password_hash
    raw = generate_raw_token()
    await PasswordResetTokenRepository(db_session).add(
        user_id=uid, token_hash=hash_token(raw), expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    await db_session.commit()
    # Two clients open at once, so two independent apps (see make_app).
    with client_for(make_app(), raise_server_exceptions=False) as other_device:
        login(other_device, email)
        with client_for(make_app(), raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": raw, "new_password": "a-brand-new-password"},
            )
    db_session.expire_all()
    row = await db_session.get(UserModel, uid)
    live = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == uid, SessionModel.revoked_at.is_(None))
    )
    assert row is not None and row.password_hash == old_hash, "the reset must really be absent"
    assert live == 1
    assert_problem(response, 500, "INTERNAL_ERROR")
