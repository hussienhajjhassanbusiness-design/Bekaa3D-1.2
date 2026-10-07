"""Regressions for three review findings on VS-005.

Each test here fails against the branch as originally written:

- an accepted TOTP could be presented a second time inside its ~90-second
  window (RFC 6238 5.2);
- `/auth/mfa/setup/confirm` could be replayed against an already-enabled
  credential, rotating the recovery-code set without the password that
  `/auth/mfa/recovery-codes/regenerate` demands;
- reaching the MFA challenge with a correct administrator password wrote no
  audit row at all (BR-132).
"""

from datetime import UTC, datetime

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.security.totp import current_step
from app.identity.infrastructure.models import MfaCredentialModel, MfaRecoveryCodeModel
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_login import PASSWORD
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

VERIFY_PATH = "/api/v1/auth/mfa/verify"
CONFIRM_PATH = "/api/v1/auth/mfa/setup/confirm"
LOGIN_PATH = "/api/v1/auth/login"


# --------------------------------------------------------------------------
# TOTP replay
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_same_totp_cannot_authenticate_twice(db_session: AsyncSession) -> None:
    """The finding, end to end.

    A code stays valid for roughly 90 seconds. An attacker who captures one -
    a phishing proxy, a shoulder-surf - and also holds the password could
    previously spend it a second time, which is exactly the interception the
    second factor exists to survive. Each attempt uses its own challenge, since
    challenges are single-use, so what is proven here is the *code* being
    refused rather than the challenge.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        code = login_totp(secret)

        first = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )
        second = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )

    assert first.status_code == 204, first.text
    assert second.status_code == 401, second.text
    # Indistinguishable from a code that was simply wrong: telling the caller
    # it was "already used" confirms they hold a real code.
    assert second.json()["code"] == "MFA_INVALID"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_guard_rejects_the_spent_step_without_latching(
    db_session: AsyncSession,
) -> None:
    """Forward progress: a credential that authenticated earlier must still
    accept a current code, or the guard would lock the administrator out
    permanently after their first login.

    The verifier's window is only one step wide either way, so three distinct
    usable steps cannot be reached from one wall-clock instant without sleeping
    for 30 seconds. Instead the credential's mark is aged backwards in the
    database - the same state a login two minutes ago would have left - and the
    current code is then presented normally through the endpoint.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        credential = await db_session.scalar(
            select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
        )
        assert credential is not None
        credential.last_totp_step = current_step(datetime.now(UTC)) - 4
        await db_session.commit()

        code = pyotp.TOTP(secret).now()
        accepted = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )
        # ...and that same code is spent the moment it is accepted.
        replayed = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )

    assert accepted.status_code == 204, accepted.text
    assert replayed.status_code == 401


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_spent_code_does_not_lock_out_the_recovery_path(
    db_session: AsyncSession,
) -> None:
    """Rejecting a replayed code must not strand an administrator: the recovery
    sheet is the fallback and has to keep working."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, codes = enrol_admin(client)

        code = login_totp(secret)
        client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )
        replayed = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )
        recovered = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )

    assert replayed.status_code == 401
    assert recovered.status_code == 204, recovered.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_detected_replay_is_audited_without_recording_the_code(
    db_session: AsyncSession,
) -> None:
    """A wrong code is noise; a *correct* code arriving twice means one was
    captured, and an operator has to be able to see that.

    The row must carry no redeemable material - not the OTP, not the secret.
    The time-step identifies which 30-second bucket without being usable for
    anything, which is exactly the level of detail an investigation needs."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        code = login_totp(secret)
        client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )
        replayed = client.post(
            VERIFY_PATH, json={"challenge_id": login_challenged(client, email), "code": code}
        )

    assert replayed.status_code == 401
    # The caller is told nothing that separates this from a plain wrong code.
    assert replayed.json()["code"] == "MFA_INVALID"
    assert "replay" not in replayed.text.lower()

    rows = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.actor_user_id == user.id,
                AuditLogModel.action == "mfa.replay_rejected",
            )
        )
    ).all()

    # Written despite the request failing: get_session runs one transaction per
    # request, so this row only survives because the route commits it before
    # raising.
    assert len(rows) == 1
    row = rows[0]
    assert row.after_data is not None
    assert set(row.after_data) == {"time_step"}
    assert isinstance(row.after_data["time_step"], int)
    # Nothing redeemable anywhere in the row.
    assert code not in str(row.after_data)
    assert secret not in str(row.after_data)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_recovery_code_does_not_spend_a_totp_step(db_session: AsyncSession) -> None:
    """The two are separate one-time credentials. Redeeming a recovery code
    must leave `last_totp_step` untouched, or a TOTP in the same 30-second
    bucket would be refused for no reason."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, codes = enrol_admin(client)

        credential = await db_session.scalar(
            select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
        )
        assert credential is not None
        # Aged backwards first, and this is the point of the test rather than
        # incidental setup: enrollment leaves the mark at the *current* step,
        # so a recovery redemption that wrongly spent a step would write that
        # same number and the assertion below would pass for the wrong reason.
        # From a distinctly older value, any write at all is visible.
        aged_step = current_step(datetime.now(UTC)) - 5
        credential.last_totp_step = aged_step
        await db_session.commit()

        recovered = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )
        assert recovered.status_code == 204, recovered.text

        await db_session.refresh(credential)
        step_after_recovery = credential.last_totp_step
        last_used = credential.last_used_at

        # And a TOTP still works straight afterwards.
        accepted = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "code": login_totp(secret)},
        )

    assert step_after_recovery == aged_step
    # It still counted as a use of the credential, just not of a TOTP step.
    assert last_used is not None
    assert accepted.status_code == 204, accepted.text


# --------------------------------------------------------------------------
# Repeated confirmation
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_confirming_again_is_refused_once_mfa_is_enabled(
    db_session: AsyncSession,
) -> None:
    """`/setup/confirm` was a second door to recovery-code regeneration, and a
    weaker one: it needed only an admin session and a valid TOTP, where
    `/recovery-codes/regenerate` requires the account password."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, original_codes = enrol_admin(client)

        repeated = client.post(
            CONFIRM_PATH,
            json={"code": pyotp.TOTP(secret).now()},
            headers=csrf_headers(client),
        )

    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["code"] == "INVALID_STATE_TRANSITION"
    # And no fresh set leaked into the response.
    assert "recovery_codes" not in repeated.text

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    unused = (
        await db_session.scalars(
            select(MfaRecoveryCodeModel).where(
                MfaRecoveryCodeModel.mfa_credential_id == credential.id,
                MfaRecoveryCodeModel.used_at.is_(None),
            )
        )
    ).all()
    # The printed sheet is intact: as many live codes as were issued.
    assert len(unused) == len(original_codes)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_original_recovery_codes_still_work_after_a_repeated_confirm(
    db_session: AsyncSession,
) -> None:
    """The previous test stated as consequence rather than row count: a refused
    re-confirmation must not have invalidated the sheet."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, codes = enrol_admin(client)

        client.post(
            CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf_headers(client)
        )
        used = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )

    assert used.status_code == 204, used.text


# --------------------------------------------------------------------------
# Challenge audit
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reaching_the_mfa_challenge_is_audited(db_session: AsyncSession) -> None:
    """BR-132: auth events are audit-logged. A correct password on an
    administrator account is one, and it previously left no trace unless the
    second factor was also cleared - so a stolen admin password could be
    confirmed working, repeatedly, invisibly."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)
        login_challenged(client, email)

    actions = list(
        (
            await db_session.scalars(
                select(AuditLogModel.action).where(AuditLogModel.actor_user_id == user.id)
            )
        ).all()
    )

    assert "user.mfa_challenge_issued" in actions
    # Distinct from user.logged_in on purpose: no session was created by the
    # challenge, and recording one would make "when did this account sign in?"
    # answer wrongly. The single logged_in row is the pre-enrollment login.
    assert actions.count("user.logged_in") == 1, actions


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_wrong_password_does_not_write_a_challenge_audit_row(
    db_session: AsyncSession,
) -> None:
    """The row must mean "this password was correct". If a failed login wrote
    it too, it would be worthless as a signal."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        client.cookies.clear()
        refused = client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD + "-wrong"})

    assert refused.status_code == 401

    actions = list(
        (
            await db_session.scalars(
                select(AuditLogModel.action).where(AuditLogModel.actor_user_id == user.id)
            )
        ).all()
    )
    assert actions.count("user.mfa_challenge_issued") == 0
