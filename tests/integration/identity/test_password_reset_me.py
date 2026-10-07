"""VS-006 `/api/v1/me` across a password reset.

Two halves of one guarantee. Authentication issued *before* a reset must stop
working the moment the reset completes - not at the next refresh - and
authentication issued *after* it must work normally. The second half is what
stops the first from being satisfied by simply breaking `/me`.

Before ADR-018 the first half was false: `current_claims` trusted the signed
access token for its full fifteen minutes and never consulted the `sessions`
row, so a revoked session kept reading `/me` until the token happened to expire.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.application.services.password_reset import PASSWORD_RESET_TOKEN_TTL
from app.identity.infrastructure.models import PasswordResetTokenModel, SessionModel
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import unique_email

ME_PATH = "/api/v1/me"
CONFIRM_PATH = "/api/v1/auth/password-reset/confirm"
LOGIN_PATH = "/api/v1/auth/login"

NEW_PASSWORD = "a-completely-different-password"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_old_session_cannot_read_me_after_a_password_reset(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        assert (
            client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD}).status_code == 200
        )

        before = client.get(ME_PATH)
        assert before.status_code == 200, before.text

        raw = generate_raw_token()
        db_session.add(
            PasswordResetTokenModel(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL,
            )
        )
        await db_session.commit()

        # The reset clears cookies on *this* client, which would make the check
        # below trivially pass for the wrong reason. Put them back: the question
        # is whether the server still honours the credential, not whether this
        # particular browser kept a copy.
        cookies_before_reset = dict(client.cookies)
        reset = client.post(CONFIRM_PATH, json={"token": raw, "new_password": NEW_PASSWORD})
        assert reset.status_code == 204, reset.text
        for name, value in cookies_before_reset.items():
            client.cookies.set(name, value)

        after = client.get(ME_PATH)

    live = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None))
    )
    # The session row really was revoked - so anything that still works is
    # working despite the revocation, not because it was missed.
    assert live == 0

    assert after.status_code == 401, (
        "an access token minted before the reset still authenticates: "
        f"GET /me returned {after.status_code}"
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_token_minted_after_the_reset_works_normally(
    db_session: AsyncSession,
) -> None:
    """The other half: the epoch check must reject stale credentials without
    rejecting current ones.

    An implementation that refused every token for an account that had ever
    reset would satisfy the test above and be completely broken, and this is
    what catches that.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)

        raw = generate_raw_token()
        db_session.add(
            PasswordResetTokenModel(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL,
            )
        )
        await db_session.commit()

        reset = client.post(CONFIRM_PATH, json={"token": raw, "new_password": NEW_PASSWORD})
        assert reset.status_code == 204, reset.text

        # A fresh login with the new password, which mints a token stamped at
        # the epoch the reset just moved to.
        logged_in = client.post(LOGIN_PATH, json={"email": email, "password": NEW_PASSWORD})
        assert logged_in.status_code == 200, logged_in.text

        after = client.get(ME_PATH)

    assert after.status_code == 200, after.text
    assert after.json()["email"] == email
