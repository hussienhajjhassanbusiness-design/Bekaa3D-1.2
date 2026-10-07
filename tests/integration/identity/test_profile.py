import uuid
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import UserModel
from tests.integration.identity.test_login import PASSWORD, register_and_verify

PROFILE_PATH = "/api/v1/me"


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200


async def _register_unverified(
    client: TestClient, db_session: AsyncSession, email: str
) -> UserModel:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 202
    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    await db_session.refresh(user)
    return user


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_verified_customer_reads_their_own_profile(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)
        response = client.get(PROFILE_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == email
    assert body["role"] == "customer"
    assert body["email_verified"] is True
    assert body["email_verified_at"] is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unverified_customer_may_read_their_profile(db_session: AsyncSession) -> None:
    """api-endpoints.md 9.1: "Read allowed while unverified". Verification gates
    protected *writes*, and this endpoint has none."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await _register_unverified(client, db_session, email)
        _login(client, email)
        response = client.get(PROFILE_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email_verified"] is False
    assert body["email_verified_at"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_each_session_only_ever_sees_its_own_profile(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    """Ownership (FR-03: "A customer cannot view another customer's profile").
    The subject comes from the signed token, so there is no identifier to
    tamper with - this proves two live sessions cannot cross over.

    Both clients are open at once, so each needs its own app instance: two
    lifespans over the shared `app.main.app` singleton overwrite one another's
    `app.state` and deadlock the first client's next request."""
    first_email = _unique_email()
    second_email = _unique_email()
    with TestClient(make_app()) as first_client, TestClient(make_app()) as second_client:
        first_user = await register_and_verify(first_client, db_session, first_email)
        second_user = await register_and_verify(second_client, db_session, second_email)
        _login(first_client, first_email)
        _login(second_client, second_email)

        first_body = first_client.get(PROFILE_PATH).json()
        second_body = second_client.get(PROFILE_PATH).json()

    assert first_body["id"] == str(first_user.id)
    assert first_body["email"] == first_email
    assert second_body["id"] == str(second_user.id)
    assert second_body["email"] == second_email
    assert first_body["id"] != second_body["id"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_profile_never_exposes_credentials_or_internal_columns(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        _login(client, email)
        body = client.get(PROFILE_PATH).json()

    assert set(body) == {"id", "email", "role", "email_verified", "email_verified_at", "created_at"}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reading_the_profile_needs_no_csrf_header(db_session: AsyncSession) -> None:
    """GET is a safe method, so the double-submit check must not apply to it -
    otherwise a plain page load would fail. Guards against it being added.

    `client.get` sends no X-CSRF-Token header, which is exactly the condition
    `require_csrf` rejects with 403."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        _login(client, email)
        response = client.get(PROFILE_PATH)

    assert response.status_code == 200
    assert "X-CSRF-Token" not in response.request.headers


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_reading_the_profile_without_a_session_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get(PROFILE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_forged_access_token_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.set("access_token", "not.a.jwt")
        response = client.get(PROFILE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_account_cannot_read_its_profile(db_session: AsyncSession) -> None:
    """The access token stays signed and unexpired, but the account behind it
    no longer authenticates - personal data must not keep being served for the
    rest of the token's life."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)
        assert client.get(PROFILE_PATH).status_code == 200

        row = await db_session.scalar(select(UserModel).where(UserModel.id == user.id))
        assert row is not None
        row.is_active = False
        await db_session.commit()

        response = client.get(PROFILE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
