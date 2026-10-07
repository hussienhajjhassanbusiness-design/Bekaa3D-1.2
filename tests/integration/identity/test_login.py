import uuid

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.application.services.login_throttle import LOCKOUT_AT_ATTEMPT, LoginThrottle
from app.identity.infrastructure.models import SessionModel, UserModel
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel

PASSWORD = "correct-horse-battery"

# Starlette's TestClient presents this as the client host, and the throttle and
# rate limiter both key on it.
TEST_CLIENT_IP = "testclient"


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


def cookie_value(response: Response, name: str) -> str | None:
    """Read a cookie straight off Set-Cookie rather than from the client jar,
    so tests can assert on the raw attributes the browser would see."""
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw.split("=", 1)[1].split(";", 1)[0]
    return None


def cookie_header(response: Response, name: str) -> str | None:
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw
    return None


async def register_and_verify(
    client: TestClient, db_session: AsyncSession, email: str, password: str = PASSWORD
) -> UserModel:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    outbox = await db_session.scalar(
        select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
    )
    assert outbox is not None
    assert client.post("/api/v1/auth/verify-email", json={"token": outbox.payload["token"]})
    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    await db_session.refresh(user)
    return user


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_login_creates_a_session_and_sets_three_cookies(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == email
    assert body["role"] == "customer"
    assert body["email_verified"] is True

    # The tokens must never appear in the response body - only in cookies.
    assert "access_token" not in body
    assert "refresh_token" not in body

    session = await db_session.scalar(select(SessionModel).where(SessionModel.user_id == user.id))
    assert session is not None
    assert session.token_version == 1
    assert session.revoked_at is None
    assert session.refresh_token_hash != cookie_value(response, "refresh_token")

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.actor_user_id == user.id, AuditLogModel.action == "user.logged_in"
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_cookie_flags_match_the_security_contract(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    access = cookie_header(response, "access_token")
    refresh = cookie_header(response, "refresh_token")
    csrf = cookie_header(response, "csrf_token")
    assert access and refresh and csrf

    # Credentials must be unreadable by JavaScript (SEC-02/ADR-006).
    assert "HttpOnly" in access
    assert "HttpOnly" in refresh
    # ...and the CSRF token must be readable, or double-submit cannot work.
    assert "HttpOnly" not in csrf

    assert "SameSite=lax" in access
    assert "SameSite=lax" in refresh

    # The long-lived credential is scoped to the auth routes only.
    assert "Path=/api/v1/auth" in refresh
    assert "Path=/" in access

    settings = get_settings()
    assert settings.access_token_minutes * 60 == int(access.split("Max-Age=")[1].split(";")[0])
    assert settings.refresh_token_days * 86400 == int(refresh.split("Max-Age=")[1].split(";")[0])


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_unknown_email_and_wrong_password_are_indistinguishable(
    db_session: AsyncSession,
) -> None:
    """FR-02: authentication errors must not reveal whether an email exists."""
    from app.main import app

    known = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, known)

        wrong_password = client.post(
            "/api/v1/auth/login", json={"email": known, "password": "definitely-not-it"}
        )
        unknown_email = client.post(
            "/api/v1/auth/login", json={"email": _unique_email(), "password": PASSWORD}
        )

    assert wrong_password.status_code == unknown_email.status_code == 401

    a, b = wrong_password.json(), unknown_email.json()
    # request_id differs per request by design; everything else must match.
    a.pop("request_id"), b.pop("request_id")
    assert a == b
    assert a["code"] == "INVALID_CREDENTIALS"

    # A failed login must not have created a session for the real account.
    user = await db_session.scalar(select(UserModel).where(UserModel.email == known))
    assert user is not None
    sessions = (
        await db_session.scalars(select(SessionModel).where(SessionModel.user_id == user.id))
    ).all()
    assert sessions == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unverified_account_can_still_log_in(db_session: AsyncSession) -> None:
    """Verification gates protected *writes*, not the front door
    (entities-and-business-rules.md: unverified users may browse)."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["email_verified"] is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_account_is_refused_with_a_distinct_code(
    db_session: AsyncSession,
) -> None:
    """Specific only *after* the password verified - someone who already knows
    the password learns nothing new, so this stays enumeration-safe."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        user.is_active = False
        await db_session.commit()

        refused = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        wrong_password = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "definitely-not-it"}
        )

    assert refused.status_code == 403
    assert refused.json()["code"] == "ACCOUNT_DISABLED"

    # The disabled state is invisible to anyone who does not know the password.
    assert wrong_password.status_code == 401
    assert wrong_password.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_lockout_returns_429_with_retry_after(db_session: AsyncSession) -> None:
    """SEC-05. The counter is pre-seeded rather than earned through ten real
    attempts, because the progressive delay would make that take ~40 seconds."""
    from app.main import app

    email = _unique_email()
    settings = get_settings()
    redis = redis_asyncio.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    try:
        with TestClient(app) as client:
            await register_and_verify(client, db_session, email)
            # One short of the threshold, so the request below is exactly the
            # attempt the lockout is supposed to start at - seeding higher
            # would pass even if the boundary were off by one.
            await redis.set(LoginThrottle._key(email, TEST_CLIENT_IP), LOCKOUT_AT_ATTEMPT - 1)

            # Even the correct password is refused while locked out.
            response = client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
    finally:
        await redis.aclose()

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_successful_login_clears_the_failure_counter(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    settings = get_settings()
    redis = redis_asyncio.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    key = LoginThrottle._key(email, TEST_CLIENT_IP)
    try:
        with TestClient(app) as client:
            await register_and_verify(client, db_session, email)
            client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
            assert await redis.get(key) == b"1"

            client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert await redis.get(key) is None
    finally:
        await redis.aclose()
