import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.security.secret_cipher import decrypt_secret
from app.identity.application.security.totp import TOTP_STEP_SECONDS
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import (
    MfaCredentialModel,
    MfaRecoveryCodeModel,
    UserModel,
)
from tests.integration.identity.test_login import PASSWORD, register_and_verify

SETUP_PATH = "/api/v1/auth/mfa/setup"
CONFIRM_PATH = "/api/v1/auth/mfa/setup/confirm"


def unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


async def make_admin(client: TestClient, db_session: AsyncSession, email: str) -> UserModel:
    """Register, verify, then promote to administrator.

    The promotion happens before login on purpose: the role is baked into the
    access token at login, so flipping it afterwards would leave the client
    holding a customer token."""
    user = await register_and_verify(client, db_session, email)
    row = await db_session.scalar(select(UserModel).where(UserModel.id == user.id))
    assert row is not None
    row.role = UserRole.ADMIN
    await db_session.commit()
    await db_session.refresh(row)
    return row


def login(client: TestClient, email: str, password: str = PASSWORD) -> None:
    """An ordinary login that ends in a session: customers, and administrators
    who have not yet confirmed enrollment."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def login_challenged(client: TestClient, email: str, password: str = PASSWORD) -> str:
    """Log in as an administrator with MFA enabled, and return the challenge id.

    Clears the cookie jar first. TestClient keeps cookies across requests, so
    without this a session left over from an earlier login would still be
    sitting in the jar and any assertion about "no cookies before MFA" would
    pass for the wrong reason."""
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 202, response.text
    return str(response.json()["challenge_id"])


def csrf_headers(client: TestClient) -> dict[str, str]:
    """The double-submit header. Every MFA route is an authenticated POST, so
    SEC-03 applies to all of them."""
    token = client.cookies.get("csrf_token")
    assert token is not None
    return {"X-CSRF-Token": token}


def start_enrollment(client: TestClient) -> dict[str, str]:
    response = client.post(
        SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
    )
    assert response.status_code == 200, response.text
    body: dict[str, str] = response.json()
    return body


def login_totp(secret: str) -> str:
    """A code for the step *after* the current one, for logging in after
    enrollment.

    `/setup/confirm` accepts a real TOTP, so that code's time-step is spent -
    RFC 6238 5.2 forbids accepting the same OTP twice, and the replay guard
    enforces it. These tests enrol and then immediately log in inside the same
    30-second bucket, so they need the next step's code.

    No administrator hits this in practice: `/setup/confirm` already leaves the
    session MFA-complete, so nobody logs in again a second after enrolling. The
    +1 step is inside the drift window the verifier accepts, so no test has to
    sleep for it."""
    return pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=TOTP_STEP_SECONDS))


def enrol_admin(client: TestClient) -> tuple[str, list[str]]:
    """Complete enrollment. Returns the TOTP secret and the recovery codes."""
    secret = start_enrollment(client)["secret"]
    response = client.post(
        CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf_headers(client)
    )
    assert response.status_code == 200, response.text
    return secret, list(response.json()["recovery_codes"])


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_setup_creates_a_credential_but_does_not_enable_mfa(
    db_session: AsyncSession,
) -> None:
    """database-design.md 5.6: `enabled_at` stays NULL until confirmation."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        body = start_enrollment(client)

    assert body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/")

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    assert credential.enabled_at is None
    assert credential.method == "totp"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_stored_secret_is_encrypted_not_plaintext(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret = start_enrollment(client)["secret"]

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    stored = bytes(credential.secret_ciphertext)

    assert secret.encode("utf-8") not in stored
    # ...but the server can still get it back, which is what makes TOTP work.
    assert decrypt_secret(stored) == secret


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_invalid_code_does_not_enable_mfa(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        start_enrollment(client)

        response = client.post(CONFIRM_PATH, json={"code": "000000"}, headers=csrf_headers(client))

    assert response.status_code == 422
    assert response.json()["code"] == "MFA_INVALID"

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    assert credential.enabled_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_valid_code_enables_mfa_and_issues_recovery_codes(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)

    assert len(codes) == 10
    assert len(set(codes)) == 10

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    assert credential.enabled_at is not None
    assert credential.last_used_at is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_recovery_codes_are_stored_only_as_hashes(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    stored = (
        await db_session.scalars(
            select(MfaRecoveryCodeModel).where(
                MfaRecoveryCodeModel.mfa_credential_id == credential.id
            )
        )
    ).all()

    assert len(stored) == 10
    hashes = {row.code_hash for row in stored}
    for plaintext in codes:
        assert plaintext not in hashes
        assert plaintext.replace("-", "") not in hashes
    # SHA-256 hex, as token_service produces.
    assert all(len(row.code_hash) == 64 for row in stored)
    assert all(row.used_at is None for row in stored)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_setup_requires_the_current_password(db_session: AsyncSession) -> None:
    """A hijacked session must not be enough to point the second factor at an
    attacker's authenticator."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.post(
            SETUP_PATH, json={"current_password": "wrong-password"}, headers=csrf_headers(client)
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_non_admin_gets_404_from_the_mfa_routes(db_session: AsyncSession) -> None:
    """SEC-10: an ordinary customer must not learn that admin MFA exists."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        login(client, email)
        setup = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )
        confirm = client.post(CONFIRM_PATH, json={"code": "123456"}, headers=csrf_headers(client))

    assert setup.status_code == 404
    assert setup.json()["code"] == "NOT_FOUND"
    assert confirm.status_code == 404


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_mfa_routes_reject_an_unauthenticated_caller() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(SETUP_PATH, json={"current_password": PASSWORD})

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_setup_requires_the_csrf_header(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.post(SETUP_PATH, json={"current_password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_re_enrollment_is_refused_once_mfa_is_enabled(db_session: AsyncSession) -> None:
    """One `secret_ciphertext` column cannot hold a live and a pending secret at
    once, so replacing an enabled factor is refused rather than risking a
    lockout. See MfaAlreadyEnabledError."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        response = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_restarting_an_unconfirmed_enrollment_replaces_the_pending_secret(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        first = start_enrollment(client)["secret"]
        second = start_enrollment(client)["secret"]

    assert first != second

    # Still exactly one credential - the UNIQUE on user_id holds.
    credentials = (
        await db_session.scalars(
            select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
        )
    ).all()
    assert len(credentials) == 1
    assert decrypt_secret(bytes(credentials[0].secret_ciphertext)) == second
