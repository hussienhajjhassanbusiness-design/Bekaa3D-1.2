"""Where the TOTP secret and the recovery codes are allowed to appear, and
where they must never appear.

Exactly two responses in the system may carry this material: `/setup` returns
the secret once, and `/setup/confirm` and `/recovery-codes/regenerate` return
plaintext codes once. Everything else - later responses, logs, audit rows, the
database - must be clean."""

import logging

import pyotp
import pytest
import structlog
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.identity.test_login import PASSWORD
from tests.integration.identity.test_mfa_enrollment import (
    CONFIRM_PATH,
    SETUP_PATH,
    csrf_headers,
    login,
    make_admin,
    unique_email,
)

REGENERATE_PATH = "/api/v1/auth/mfa/recovery-codes/regenerate"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_secret_appears_in_the_setup_response_and_nowhere_after(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)

        setup = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )
        secret = setup.json()["secret"]

        confirm = client.post(
            CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf_headers(client)
        )
        regenerate = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    # Once, deliberately: an authenticator cannot be provisioned without it.
    assert secret in setup.text
    # ...and never again.
    assert secret not in confirm.text
    assert secret not in regenerate.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_response_ever_exposes_the_ciphertext_or_the_code_hashes(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        setup = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )
        confirm = client.post(
            CONFIRM_PATH,
            json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
            headers=csrf_headers(client),
        )

    assert set(setup.json()) == {"secret", "otpauth_uri", "issuer", "account_name"}
    assert set(confirm.json()) == {"recovery_codes", "generated_at"}
    for body in (setup.json(), confirm.json()):
        assert "secret_ciphertext" not in body
        assert "code_hash" not in body
        assert "password" not in body
        assert "access_token" not in body
        assert "refresh_token" not in body


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_secret_or_recovery_code_reaches_the_logs(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """A secret that is safely encrypted at rest is still compromised if it was
    written to stdout on the way there."""
    from app.main import app

    email = unique_email()
    root = logging.getLogger()
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        # The app's lifespan has just run configure_logging(), which *replaces*
        # the root handlers - detaching caplog's. Without re-attaching it here
        # caplog captured nothing at all and this test could never fail.
        root.addHandler(caplog.handler)
        try:
            # Positive control: proof that whatever the app logs through its
            # own structlog configuration really lands in caplog.
            structlog.get_logger("app.tests").info("log_capture_canary")

            await make_admin(client, db_session, email)
            login(client, email)

            setup = client.post(
                SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
            )
            secret = setup.json()["secret"]
            confirm = client.post(
                CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf_headers(client)
            )
            codes = confirm.json()["recovery_codes"]
        finally:
            root.removeHandler(caplog.handler)

    logged = "\n".join(record.getMessage() for record in caplog.records)

    assert "log_capture_canary" in logged, "log capture is not working; the test proves nothing"
    assert secret not in logged
    assert PASSWORD not in logged
    for code in codes:
        assert code not in logged
        assert code.replace("-", "") not in logged
