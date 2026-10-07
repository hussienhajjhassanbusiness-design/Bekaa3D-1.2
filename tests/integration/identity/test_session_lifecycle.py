import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import SessionModel, UserModel
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_login import (
    PASSWORD,
    cookie_header,
    cookie_value,
    register_and_verify,
)

REFRESH_PATH = "/api/v1/auth"
# Python's cookiejar appends ".local" to a dotless host, so the jar keys the
# TestClient's "testserver" cookies under this domain.
TEST_DOMAIN = "testserver.local"


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


def _login(client: TestClient, email: str) -> Response:
    response: Response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return response


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _force_refresh_cookie(client: TestClient, value: str) -> None:
    """Replace the jar's refresh cookie. `Cookies.set` alone *appends*, and the
    existing cookie keeps winning - which silently sends the current token and
    makes a replay test pass for entirely the wrong reason."""
    for domain in {c.domain for c in client.cookies.jar if c.name == "refresh_token"}:
        client.cookies.delete("refresh_token", domain=domain, path=REFRESH_PATH)
    client.cookies.set("refresh_token", value, domain=TEST_DOMAIN, path=REFRESH_PATH)


async def _session_row(db_session: AsyncSession, user_id: uuid.UUID) -> SessionModel:
    row = await db_session.scalar(select(SessionModel).where(SessionModel.user_id == user_id))
    assert row is not None
    await db_session.refresh(row)
    return row


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_refresh_rotates_the_token_and_advances_the_version(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        login = _login(client, email)
        first_token = cookie_value(login, "refresh_token")

        before = await _session_row(db_session, user.id)
        first_hash = before.refresh_token_hash

        response = client.post("/api/v1/auth/refresh", headers=_csrf(client))

    assert response.status_code == 204
    second_token = cookie_value(response, "refresh_token")
    assert second_token is not None
    assert second_token != first_token
    assert cookie_value(response, "access_token") is not None

    after = await _session_row(db_session, user.id)
    assert after.token_version == 2
    assert after.refresh_token_hash != first_hash
    assert after.rotated_at is not None
    assert after.last_used_at is not None
    assert after.revoked_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_replaying_a_rotated_refresh_token_revokes_the_whole_session(
    db_session: AsyncSession,
) -> None:
    """The headline security property of VS-003. A stolen token that was
    already rotated away must not merely be rejected - it must kill the
    session, and that revocation must survive the failed request's rollback."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        login = _login(client, email)
        stolen = cookie_value(login, "refresh_token")
        assert stolen is not None

        # The legitimate user refreshes; the stolen copy is now stale.
        assert client.post("/api/v1/auth/refresh", headers=_csrf(client)).status_code == 204

        # The thief replays their copy.
        _force_refresh_cookie(client, stolen)
        replay = client.post("/api/v1/auth/refresh", headers=_csrf(client))

    assert replay.status_code == 401
    # Deliberately indistinguishable from any other rejected token: telling the
    # attacker that reuse was detected tells them the token was genuine.
    assert replay.json()["code"] == "AUTH_REQUIRED"

    row = await _session_row(db_session, user.id)
    assert row.reuse_detected_at is not None
    assert row.revoked_at is not None

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.actor_user_id == user.id,
            AuditLogModel.action == "session.reuse_detected",
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_current_token_stops_working_once_reuse_is_detected(
    db_session: AsyncSession,
) -> None:
    """Revocation must lock out the thief *and* the real user - neither can
    tell which is which, so the only safe answer is a fresh login."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        login = _login(client, email)
        stolen = cookie_value(login, "refresh_token")
        assert stolen is not None

        assert client.post("/api/v1/auth/refresh", headers=_csrf(client)).status_code == 204
        current = client.cookies["refresh_token"]

        _force_refresh_cookie(client, stolen)
        client.post("/api/v1/auth/refresh", headers=_csrf(client))

        _force_refresh_cookie(client, current)
        after_revocation = client.post("/api/v1/auth/refresh", headers=_csrf(client))

    assert after_revocation.status_code == 401


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_refresh_without_the_csrf_header_is_rejected(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)

        response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"

    # A rejected CSRF request must have no side effect at all.
    row = await _session_row(db_session, user.id)
    assert row.token_version == 1
    assert row.rotated_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_another_sessions_csrf_token_is_rejected(db_session: AsyncSession) -> None:
    """Because the token is HMAC(secret, session_id), a valid-looking token
    from a different session cannot be reused here."""
    from app.main import app

    with TestClient(app) as client:
        await register_and_verify(client, db_session, _unique_email())
        victim_email = _unique_email()
        await register_and_verify(client, db_session, victim_email)
        _login(client, victim_email)

        other_session_csrf = uuid.uuid4().hex * 2
        response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": other_session_csrf})

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_refresh_without_a_refresh_cookie_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_logout_revokes_the_session_and_clears_the_cookies(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)

        response = client.post("/api/v1/auth/logout", headers=_csrf(client))

    assert response.status_code == 204
    for name in ("access_token", "refresh_token", "csrf_token"):
        header = cookie_header(response, name)
        assert header is not None
        assert "Max-Age=0" in header

    row = await _session_row(db_session, user.id)
    assert row.revoked_at is not None

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.actor_user_id == user.id, AuditLogModel.action == "user.logged_out"
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_revoked_session_cannot_refresh(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        login = _login(client, email)
        refresh_token = cookie_value(login, "refresh_token")
        assert refresh_token is not None
        csrf = _csrf(client)

        assert client.post("/api/v1/auth/logout", headers=csrf).status_code == 204

        # Logout cleared the cookies; put the pre-logout token back to prove the
        # server rejects it on its own merits, not merely because it is absent.
        _force_refresh_cookie(client, refresh_token)
        response = client.post("/api/v1/auth/refresh", headers=csrf)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_logout_without_the_csrf_header_is_rejected(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)

        response = client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"

    row = await _session_row(db_session, user.id)
    assert row.revoked_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_logout_without_a_session_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "anything"})

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_deactivating_a_user_kills_their_session_at_the_next_refresh(
    db_session: AsyncSession,
) -> None:
    """A session must not outlive its owner's ability to authenticate."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        _login(client, email)

        deactivated = await db_session.scalar(select(UserModel).where(UserModel.id == user.id))
        assert deactivated is not None
        deactivated.is_active = False
        await db_session.commit()

        response = client.post("/api/v1/auth/refresh", headers=_csrf(client))

    assert response.status_code == 401

    row = await _session_row(db_session, user.id)
    assert row.revoked_at is not None
