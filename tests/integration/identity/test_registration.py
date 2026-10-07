import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import UserModel, VerificationTokenModel
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_new_email_creates_unverified_user_and_queues_verification(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )

    assert response.status_code == 202

    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    assert user.email_verified_at is None

    token = await db_session.scalar(
        select(VerificationTokenModel).where(VerificationTokenModel.user_id == user.id)
    )
    assert token is not None
    assert token.used_at is None

    outbox = await db_session.scalar(
        select(EmailOutboxModel).where(EmailOutboxModel.user_id == user.id)
    )
    assert outbox is not None
    assert outbox.template == "verification_email"
    assert outbox.status == "pending"
    assert "token" in outbox.payload

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.entity_id == user.id, AuditLogModel.action == "user.registered"
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_registering_the_same_email_twice_does_not_create_a_second_account(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )
        second = client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )

    # Enumeration-safe: identical response shape whether the address was new
    # or already registered.
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()

    users = (await db_session.scalars(select(UserModel).where(UserModel.email == email))).all()
    assert len(users) == 1

    # Within the resend cooldown, the second call must not have issued a
    # second verification token for the same account.
    tokens = (
        await db_session.scalars(
            select(VerificationTokenModel).where(VerificationTokenModel.user_id == users[0].id)
        )
    ).all()
    assert len(tokens) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_registering_an_already_verified_email_does_not_mutate_the_account(
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
        raw_token = outbox.payload["token"]

        verify_response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        assert verify_response.status_code == 204

        register_again = client.post(
            "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )

    assert register_again.status_code == 202

    tokens = (
        await db_session.scalars(
            select(VerificationTokenModel)
            .join(UserModel, VerificationTokenModel.user_id == UserModel.id)
            .where(UserModel.email == email)
        )
    ).all()
    # Still only the one token from the original registration - no new one
    # was issued for the now-verified account.
    assert len(tokens) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_password_below_minimum_length_is_rejected() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register", json={"email": _unique_email(), "password": "short"}
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
