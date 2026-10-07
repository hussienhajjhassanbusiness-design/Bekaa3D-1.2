import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import UserModel, VerificationTokenModel
from app.platform.infrastructure.models import EmailOutboxModel


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_resend_for_unknown_email_is_a_silent_202() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/resend-verification", json={"email": _unique_email()})

    assert response.status_code == 202


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_resend_for_verified_email_does_not_issue_a_new_token(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )
        outbox = await db_session.scalar(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
        )
        assert outbox is not None
        client.post("/api/v1/auth/verify-email", json={"token": outbox.payload["token"]})

        response = client.post("/api/v1/auth/resend-verification", json={"email": email})

    assert response.status_code == 202

    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    tokens = (
        await db_session.scalars(
            select(VerificationTokenModel).where(VerificationTokenModel.user_id == user.id)
        )
    ).all()
    assert len(tokens) == 1  # only the original registration token


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_resend_past_the_cooldown_issues_a_new_token(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )

        user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
        assert user is not None
        token_row = await db_session.scalar(
            select(VerificationTokenModel).where(VerificationTokenModel.user_id == user.id)
        )
        assert token_row is not None
        # Simulate the cooldown having already elapsed rather than sleeping in
        # the test.
        token_row.created_at = datetime.now(UTC) - timedelta(minutes=10)
        await db_session.commit()

        response = client.post("/api/v1/auth/resend-verification", json={"email": email})

    assert response.status_code == 202

    tokens = (
        await db_session.scalars(
            select(VerificationTokenModel).where(VerificationTokenModel.user_id == user.id)
        )
    ).all()
    assert len(tokens) == 2
