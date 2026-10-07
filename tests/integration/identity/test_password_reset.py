import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import (
    PasswordResetTokenModel,
    SessionModel,
    UserModel,
    VerificationTokenModel,
)
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel
from tests.integration.identity.test_login import PASSWORD, cookie_value, register_and_verify

NEW_PASSWORD = "a-completely-different-one"
REQUEST_PATH = "/api/v1/auth/password-reset/request"
CONFIRM_PATH = "/api/v1/auth/password-reset/confirm"
REFRESH_COOKIE_PATH = "/api/v1/auth"
# Python's cookiejar appends ".local" to a dotless host, so the jar keys the
# TestClient's "testserver" cookies under this domain.
TEST_DOMAIN = "testserver.local"


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


def _snapshot_session_cookies(response: Response) -> dict[str, str]:
    """Capture one login's cookies off Set-Cookie so several sessions can be
    replayed through a single client.

    Two TestClient instances would be the obvious way to model two devices, but
    each one starts its own event loop and lifespan, and the second's engine and
    Redis connections end up bound to a loop the first is closing. Snapshotting
    the jar keeps the sessions genuinely independent without that."""
    cookies = {}
    for name in ("access_token", "refresh_token", "csrf_token"):
        value = cookie_value(response, name)
        assert value is not None, f"login did not set {name}"
        cookies[name] = value
    return cookies


def _restore_session_cookies(client: TestClient, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    client.cookies.set("access_token", cookies["access_token"], domain=TEST_DOMAIN, path="/")
    client.cookies.set("csrf_token", cookies["csrf_token"], domain=TEST_DOMAIN, path="/")
    client.cookies.set(
        "refresh_token", cookies["refresh_token"], domain=TEST_DOMAIN, path=REFRESH_COOKIE_PATH
    )


async def _reset_outbox_rows(db_session: AsyncSession, email: str) -> list[EmailOutboxModel]:
    rows = await db_session.scalars(
        select(EmailOutboxModel)
        .where(
            EmailOutboxModel.recipient_email == email,
            EmailOutboxModel.template == "password_reset_email",
        )
        .order_by(EmailOutboxModel.created_at)
    )
    return list(rows)


async def _request_reset(client: TestClient, db_session: AsyncSession, email: str) -> str:
    """Run the request leg and dig the raw token out of the outbox row - the
    same path a real user takes via their inbox."""
    response = client.post(REQUEST_PATH, json={"email": email})
    assert response.status_code == 202, response.text
    rows = await _reset_outbox_rows(db_session, email)
    assert rows, "no password_reset_email queued"
    token: str = rows[-1].payload["token"]
    return token


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_reset_replaces_the_password_and_audits_the_change(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        raw_token = await _request_reset(client, db_session, email)

        confirmed = client.post(
            CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD}
        )
        assert confirmed.status_code == 204, confirmed.text

        old = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        new = client.post("/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD})

    assert old.status_code == 401
    assert old.json()["code"] == "INVALID_CREDENTIALS"
    assert new.status_code == 200

    token_row = await db_session.scalar(
        select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user.id)
    )
    assert token_row is not None
    assert token_row.used_at is not None

    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.entity_id == user.id, AuditLogModel.action == "user.password_reset"
        )
    )
    assert audit is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_reset_revokes_every_existing_session(db_session: AsyncSession) -> None:
    """SEC-08. The reason to reset a password is usually that someone else may
    have it - and an attacker who is already logged in keeps a working refresh
    token for 30 days unless the reset kills it. This is the test that would
    fail if `revoke_all_for_user` were ever dropped from the use case."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)

        devices = []
        for _ in range(2):
            client.cookies.clear()
            login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert login.status_code == 200
            devices.append(_snapshot_session_cookies(login))

        rows = await db_session.scalars(select(SessionModel).where(SessionModel.user_id == user.id))
        assert len(list(rows)) == 2

        client.cookies.clear()
        raw_token = await _request_reset(client, db_session, email)
        confirmed = client.post(
            CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD}
        )
        assert confirmed.status_code == 204, confirmed.text

        # Both devices still hold cookies that look perfectly valid to them.
        refusals = []
        for cookies in devices:
            _restore_session_cookies(client, cookies)
            refusals.append(
                client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": cookies["csrf_token"]})
            )

    assert [r.status_code for r in refusals] == [401, 401]

    live = await db_session.scalars(
        select(SessionModel).where(
            SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None)
        )
    )
    assert list(live) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_revocation_does_not_mark_the_revoked_sessions_as_stolen(
    db_session: AsyncSession,
) -> None:
    """A reset is a legitimate revocation, not theft detection. If it set
    `reuse_detected_at` too, every routine password reset would show up in the
    audit trail as a compromised session and the signal would be worthless."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200
        raw_token = await _request_reset(client, db_session, email)
        client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD})

    rows = list(
        await db_session.scalars(select(SessionModel).where(SessionModel.user_id == user.id))
    )
    assert rows
    assert all(row.revoked_at is not None for row in rows)
    assert all(row.reuse_detected_at is None for row in rows)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_address_is_accepted_and_writes_nothing(
    db_session: AsyncSession,
) -> None:
    """Enumeration safety (api-endpoints.md §5): the caller must not be able to
    tell a real address from a made-up one."""
    from app.main import app

    known = _unique_email()
    unknown = _unique_email()

    with TestClient(app) as client:
        await register_and_verify(client, db_session, known)
        known_response = client.post(REQUEST_PATH, json={"email": known})
        unknown_response = client.post(REQUEST_PATH, json={"email": unknown})

    assert known_response.status_code == unknown_response.status_code == 202
    assert known_response.json() == unknown_response.json()
    assert await _reset_outbox_rows(db_session, unknown) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_token_cannot_be_redeemed_twice(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        raw_token = await _request_reset(client, db_session, email)

        first = client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD})
        second = client.post(
            CONFIRM_PATH, json={"token": raw_token, "new_password": "yet-another-password"}
        )

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.json()["code"] == "INVALID_TOKEN"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_unknown_token_is_rejected() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            CONFIRM_PATH,
            json={"token": "not-a-real-token-" + uuid.uuid4().hex, "new_password": NEW_PASSWORD},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TOKEN"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_expired_token_is_rejected_with_410(db_session: AsyncSession) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        raw_token = await _request_reset(client, db_session, email)

        token_row = await db_session.scalar(
            select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user.id)
        )
        assert token_row is not None
        token_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

        response = client.post(
            CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD}
        )

    assert response.status_code == 410
    assert response.json()["code"] == "RESOURCE_EXPIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_verification_token_is_not_accepted_as_a_reset_token(
    db_session: AsyncSession,
) -> None:
    """The two token types live in separate tables on purpose. Proving control
    of a mailbox is not the same authority as replacing a credential, and this
    is the test that notices if they are ever merged."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        outbox = await db_session.scalar(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
        )
        assert outbox is not None
        verification_token: str = outbox.payload["token"]

        response = client.post(
            CONFIRM_PATH, json={"token": verification_token, "new_password": NEW_PASSWORD}
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TOKEN"

    # And the verification token itself is untouched - the failed attempt must
    # not have burned the user's real verification link.
    user_row = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user_row is not None
    row = await db_session.scalar(
        select(VerificationTokenModel).where(VerificationTokenModel.user_id == user_row.id)
    )
    assert row is not None
    assert row.used_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_password_below_the_minimum_length_is_rejected(db_session: AsyncSession) -> None:
    """A password set through a reset must be no weaker than one set at
    registration - both floors are 8 characters."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        raw_token = await _request_reset(client, db_session, email)

        response = client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": "short"})

        # ...and the rejected attempt must not have consumed the token.
        retry = client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD})

    assert response.status_code == 422
    assert retry.status_code == 204


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_successful_reset_burns_other_outstanding_tokens(
    db_session: AsyncSession,
) -> None:
    """A user who asked twice holds two live links. Using one must kill the
    other, or the older email stays a working way into the account for the rest
    of its hour."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        first_token = await _request_reset(client, db_session, email)

        # Straight past the cooldown rather than sleeping through it.
        oldest = await db_session.scalar(
            select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user.id)
        )
        assert oldest is not None
        oldest.created_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        second_token = await _request_reset(client, db_session, email)
        assert second_token != first_token

        confirmed = client.post(
            CONFIRM_PATH, json={"token": second_token, "new_password": NEW_PASSWORD}
        )
        assert confirmed.status_code == 204, confirmed.text

        replayed_older = client.post(
            CONFIRM_PATH, json={"token": first_token, "new_password": "third-password-attempt"}
        )

    assert replayed_older.status_code == 400
    assert replayed_older.json()["code"] == "INVALID_TOKEN"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_second_request_inside_the_cooldown_issues_no_second_token(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        first = client.post(REQUEST_PATH, json={"email": email})
        second = client.post(REQUEST_PATH, json={"email": email})

    # Identical responses - the cooldown must not be observable from outside.
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(await _reset_outbox_rows(db_session, email)) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_account_is_not_sent_a_reset_email(
    db_session: AsyncSession,
) -> None:
    """There is nothing to recover, and issuing a token would create a route
    back into an account that was deliberately closed."""
    from app.main import app

    email = _unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        user_row = await db_session.get(UserModel, user.id)
        assert user_row is not None
        user_row.is_active = False
        await db_session.commit()

        response = client.post(REQUEST_PATH, json={"email": email})

    assert response.status_code == 202
    assert await _reset_outbox_rows(db_session, email) == []
