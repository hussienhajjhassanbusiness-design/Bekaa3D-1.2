import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import UserModel, VerificationTokenModel
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


async def _register_and_get_token(client: TestClient, db_session: AsyncSession, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 202, response.text
    outbox = await db_session.scalar(
        select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
    )
    assert outbox is not None
    token: str = outbox.payload["token"]
    return token


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_valid_token_verifies_the_account_and_writes_an_audit_event(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        raw_token = await _register_and_get_token(client, db_session, email)
        response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 204

    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    assert user.email_verified_at is not None

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.entity_id == user.id, AuditLogModel.action == "user.email_verified"
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reusing_an_already_verified_token_is_rejected(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        raw_token = await _register_and_get_token(client, db_session, email)
        first = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        second = client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.json()["code"] == "INVALID_TOKEN"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_unknown_token_is_rejected() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/verify-email", json={"token": "not-a-real-token-" + uuid.uuid4().hex}
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TOKEN"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_expired_token_is_rejected_with_410(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        raw_token = await _register_and_get_token(client, db_session, email)

        token_row = await db_session.scalar(
            select(VerificationTokenModel)
            .join(UserModel, VerificationTokenModel.user_id == UserModel.id)
            .where(UserModel.email == email)
        )
        assert token_row is not None
        token_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

        response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 410
    assert response.json()["code"] == "RESOURCE_EXPIRED"
