"""What a password reset does, and does not, do to an administrator's MFA.

SEC-08 says a reset ends every pre-reset authentication state. VS-005 added a
second kind of that state which VS-004 was written before: the five-minute login
challenge issued once an administrator's password checks out. It lives in Redis
rather than in `sessions`, so revoking rows cannot reach it, and a challenge
minted with the old password would otherwise still be redeemable into a fresh
session afterwards.

The other half of the requirement is a preservation rule, and it matters just as
much: enrollment, the TOTP secret and the recovery codes must all survive. A
reset proves control of the mailbox, which is precisely what the second factor
exists to be independent of - clearing it would turn a mailbox compromise into a
full account takeover.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import REFRESH_COOKIE
from app.identity.application.security.password_hasher import verify_password
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.application.services.password_reset import PASSWORD_RESET_TOKEN_TTL
from app.identity.domain.recovery_codes import normalize_code
from app.identity.infrastructure.models import (
    MfaCredentialModel,
    MfaRecoveryCodeModel,
    PasswordResetTokenModel,
    SessionModel,
)
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

CONFIRM_PATH = "/api/v1/auth/password-reset/confirm"
VERIFY_PATH = "/api/v1/auth/mfa/verify"
REGENERATE_PATH = "/api/v1/auth/mfa/recovery-codes/regenerate"

NEW_PASSWORD = "a-completely-different-password"


async def _code_is_unused(db_session: AsyncSession, credential_id: uuid.UUID, code: str) -> bool:
    """Whether one specific recovery code is still redeemable."""
    used_at = await db_session.scalar(
        select(MfaRecoveryCodeModel.used_at).where(
            MfaRecoveryCodeModel.mfa_credential_id == credential_id,
            MfaRecoveryCodeModel.code_hash == hash_token(normalize_code(code)),
        )
    )
    return used_at is None


async def _issue_reset_token(db_session: AsyncSession, user_id: uuid.UUID) -> str:
    """Mint a live reset token directly.

    Going through `/password-reset/request` would work, but it deliberately
    answers 202 whether or not anything was issued, so the test would have to
    dig the token back out of the outbox to learn it. Writing the row is the
    same thing with the enumeration-safety theatre removed.
    """
    raw = generate_raw_token()
    db_session.add(
        PasswordResetTokenModel(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL,
        )
    )
    await db_session.commit()
    return raw


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_reset_ends_every_pre_reset_credential_but_keeps_the_second_factor(
    db_session: AsyncSession,
) -> None:
    """The whole lifecycle in one pass, because the point is the combination.

    Asserting these separately would let a change that satisfies each in
    isolation - say, clearing MFA along with the sessions - still pass.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, recovery_codes = enrol_admin(client)

        # An outstanding challenge, minted with the old password and never
        # redeemed. This is the artefact `sessions` cannot see.
        stale_challenge = login_challenged(client, email)

        # A live session, established the ordinary way.
        challenge = login_challenged(client, email)
        completed = client.post(
            VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
        )
        assert completed.status_code == 204, completed.text
        assert client.cookies.get(REFRESH_COOKIE) is not None

        raw_token = await _issue_reset_token(db_session, user.id)
        reset = client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD})
        assert reset.status_code == 204, reset.text

        # 1. The pre-reset challenge must not buy a session.
        #
        #    Submitted with a *recovery code*, deliberately. A TOTP here proves
        #    nothing: the successful login above already spent this time-step,
        #    so VS-005's replay guard would refuse it whether or not the
        #    challenge had been invalidated, and this assertion would pass for
        #    the wrong reason. A recovery code is unspent and would be accepted
        #    on its own merits, so the only thing that can refuse it is the
        #    reset.
        stale = client.post(
            VERIFY_PATH,
            json={"challenge_id": stale_challenge, "recovery_code": recovery_codes[1]},
        )

        # 2. A fresh login with the new password still stops at a challenge -
        #    the reset did not quietly disable the second factor.
        #
        #    Completed with a recovery code rather than a TOTP, and not for
        #    convenience: the successful login above already spent this
        #    time-step, and VS-005's replay guard correctly refuses the same OTP
        #    twice. Waiting the step out would put 30 seconds into the suite for
        #    nothing, and the recovery code proves the more interesting half
        #    anyway - that codes issued before the reset still work after it.
        fresh_challenge = login_challenged(client, email, password=NEW_PASSWORD)
        fresh = client.post(
            VERIFY_PATH,
            json={"challenge_id": fresh_challenge, "recovery_code": recovery_codes[0]},
        )
        # 3. Enrollment, secret and recovery codes all survive. Counted here,
        #    before the admin probe below: that probe is
        #    `recovery-codes/regenerate`, the only production route behind the
        #    VS-005 admin boundary, and regenerating replaces the whole unused
        #    set - so counting afterwards would measure the probe rather than
        #    the reset.
        credential = await db_session.scalar(
            select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
        )
        assert credential is not None
        assert credential.enabled_at is not None
        unused_codes = await db_session.scalar(
            select(func.count())
            .select_from(MfaRecoveryCodeModel)
            .where(
                MfaRecoveryCodeModel.mfa_credential_id == credential.id,
                MfaRecoveryCodeModel.used_at.is_(None),
            )
        )

        stale_code_unused = await _code_is_unused(db_session, credential.id, recovery_codes[1])

        # 4. The session really is admin-usable: MFA-complete, not merely
        #    authenticated.
        admin_route = client.post(
            REGENERATE_PATH,
            json={"current_password": NEW_PASSWORD},
            headers=csrf_headers(client),
        )

    assert stale.status_code in (401, 410), stale.text

    # The code the refused challenge carried was never examined, so it is still
    # available - the challenge died before the factor was ever looked at.
    assert stale_code_unused, "a refused challenge must not spend a recovery code"

    # The post-reset login completes normally, on the pre-reset credential.
    assert fresh.status_code == 204, fresh.text
    assert admin_route.status_code == 200, admin_route.text
    # One was redeemed to complete the post-reset login; the rest are untouched.
    # The reset did not clear the set.
    assert unused_codes == len(recovery_codes) - 1

    # 5. Every session that existed before the reset is revoked.
    live_sessions = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None))
    )
    # Only the session the post-reset login created is still alive.
    assert live_sessions == 1

    await db_session.refresh(user)
    assert verify_password(password=NEW_PASSWORD, password_hash=user.password_hash)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_challenge_issued_after_the_reset_is_unaffected(
    db_session: AsyncSession,
) -> None:
    """The invalidation is a point in time, not a permanent disablement.

    The epoch marker is per-account and only ever moves forward, so it must void
    what came before it and nothing after. Without this, the obvious
    implementation mistake - refusing every challenge once an account has ever
    reset - would go unnoticed, and the administrator could never log in again.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        raw_token = await _issue_reset_token(db_session, user.id)
        reset = client.post(CONFIRM_PATH, json={"token": raw_token, "new_password": NEW_PASSWORD})
        assert reset.status_code == 204, reset.text

        challenge = login_challenged(client, email, password=NEW_PASSWORD)
        verified = client.post(
            VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
        )

    assert verified.status_code == 204, verified.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_second_reset_voids_challenges_issued_after_the_first(
    db_session: AsyncSession,
) -> None:
    """Two resets in a row. The marker has to keep moving.

    A first-write-wins implementation - `SET` where `INCR` was needed - would
    void the first batch of challenges and then silently stop working, which is
    exactly the sort of thing that only shows up on the second use.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        first_token = await _issue_reset_token(db_session, user.id)
        assert (
            client.post(
                CONFIRM_PATH, json={"token": first_token, "new_password": NEW_PASSWORD}
            ).status_code
            == 204
        )

        # Minted after the first reset, so the first reset cannot be what voids it.
        challenge = login_challenged(client, email, password=NEW_PASSWORD)

        second_token = await _issue_reset_token(db_session, user.id)
        assert (
            client.post(
                CONFIRM_PATH,
                json={"token": second_token, "new_password": "third-password-entirely"},
            ).status_code
            == 204
        )

        stale = client.post(
            VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
        )

    assert stale.status_code in (401, 410), stale.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_expired_reset_token_leaves_challenges_alone(
    db_session: AsyncSession,
) -> None:
    """Invalidation happens on a *successful* reset, not on an attempted one.

    A failed redemption proves nothing about who is holding the mailbox, so it
    must not be usable to knock an administrator's in-flight login over. That
    would be a free denial-of-service against anyone whose address is known.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        raw = generate_raw_token()
        db_session.add(
            PasswordResetTokenModel(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await db_session.commit()

        challenge = login_challenged(client, email)
        expired = client.post(CONFIRM_PATH, json={"token": raw, "new_password": NEW_PASSWORD})
        still_good = client.post(
            VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
        )

    assert expired.status_code == 410, expired.text
    assert still_good.status_code == 204, still_good.text
