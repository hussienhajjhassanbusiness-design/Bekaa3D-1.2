"""`POST /auth/mfa/verify`: the second half of a login-gated admin sign-in.

Under the flow api-endpoints.md:252 and :270 describe, an administrator with
MFA enabled never receives a session from `/auth/login` - only a challenge.
This endpoint is what turns a cleared second factor into the real thing, so
every test here is ultimately asking the same question: can anything short of a
correct second factor produce a usable admin session?"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.identity.application.security.session_tokens import decode_access_token
from app.identity.infrastructure.models import MfaCredentialModel, MfaRecoveryCodeModel
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_login import PASSWORD, register_and_verify
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
REGENERATE_PATH = "/api/v1/auth/mfa/recovery-codes/regenerate"
LOGIN_PATH = "/api/v1/auth/login"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_valid_totp_completes_the_login(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        challenge_id = login_challenged(client, email)
        verified = client.post(
            VERIFY_PATH,
            json={"challenge_id": challenge_id, "code": login_totp(secret)},
        )
        # The admin boundary is the real proof that a usable session exists.
        allowed = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert verified.status_code == 204
    assert allowed.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_challenge_response_carries_no_session_of_any_kind(
    db_session: AsyncSession,
) -> None:
    """The whole point of the login-gated flow: a correct password on its own
    must not produce a session, a CSRF token, or anything else usable."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        client.cookies.clear()
        response = client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD})

        # Nothing set on the response, and nothing left in the jar.
        assert response.status_code == 202, response.text
        assert response.cookies.get(ACCESS_COOKIE) is None
        assert response.cookies.get(REFRESH_COOKIE) is None
        assert response.cookies.get(CSRF_COOKIE) is None
        assert client.cookies.get(ACCESS_COOKIE) is None
        assert client.cookies.get(REFRESH_COOKIE) is None
        assert client.cookies.get(CSRF_COOKIE) is None

        body = response.json()
        assert set(body) == {"challenge_id", "expires_in_seconds"}
        assert body["expires_in_seconds"] == 300
        # Half-authenticated callers learn nothing about the account.
        assert email not in response.text

        # And the challenge alone opens no door.
        blocked = client.post(REGENERATE_PATH, json={"current_password": PASSWORD})
        assert blocked.status_code == 401
        assert blocked.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_verification_sets_the_full_cookie_set_with_the_mfa_claim(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        challenge_id = login_challenged(client, email)
        response = client.post(
            VERIFY_PATH,
            json={"challenge_id": challenge_id, "code": login_totp(secret)},
        )

        assert response.status_code == 204
        access = client.cookies.get(ACCESS_COOKIE)
        assert access is not None
        assert client.cookies.get(REFRESH_COOKIE) is not None
        assert client.cookies.get(CSRF_COOKIE) is not None

    claims = decode_access_token(access)
    assert claims.user_id == user.id
    # Born MFA-complete: there is no window where this session lacks the claim.
    assert claims.mfa_completed is True


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_invalid_totp_returns_the_stable_mfa_error(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        challenge_id = login_challenged(client, email)
        response = client.post(VERIFY_PATH, json={"challenge_id": challenge_id, "code": "000000"})

        assert response.status_code == 401
        assert response.json()["code"] == "MFA_INVALID"
        # A rejected factor leaves the caller exactly as unauthenticated as before.
        assert client.cookies.get(ACCESS_COOKIE) is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_challenge_is_gone(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)
        login_challenged(client, email)

        response = client.post(
            VERIFY_PATH,
            json={"challenge_id": "never-issued", "code": login_totp(secret)},
        )

    assert response.status_code == 410
    assert response.json()["code"] == "RESOURCE_EXPIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_challenge_cannot_be_replayed(db_session: AsyncSession) -> None:
    """Single-use, spent on the attempt rather than on success - so a wrong
    guess cannot be retried against the same challenge."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        challenge_id = login_challenged(client, email)
        first = client.post(VERIFY_PATH, json={"challenge_id": challenge_id, "code": "000000"})
        replayed = client.post(
            VERIFY_PATH,
            json={"challenge_id": challenge_id, "code": login_totp(secret)},
        )

    assert first.status_code == 401
    assert replayed.status_code == 410


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_successful_challenge_is_also_spent(db_session: AsyncSession) -> None:
    """A challenge that worked cannot be replayed into a second session."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        challenge_id = login_challenged(client, email)
        code = login_totp(secret)
        first = client.post(VERIFY_PATH, json={"challenge_id": challenge_id, "code": code})
        client.cookies.clear()
        second = client.post(VERIFY_PATH, json={"challenge_id": challenge_id, "code": code})

    assert first.status_code == 204
    assert second.status_code == 410


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_challenge_only_ever_logs_in_the_account_it_was_issued_for(
    db_session: AsyncSession,
) -> None:
    """The account comes from the challenge, never from the request, so holding
    one administrator's challenge cannot produce another's session."""
    from app.main import app

    first_email, second_email = unique_email(), unique_email()
    with TestClient(app) as client:
        first_user = await make_admin(client, db_session, first_email)
        login(client, first_email)
        first_secret, _ = enrol_admin(client)

        await make_admin(client, db_session, second_email)
        login(client, second_email)
        enrol_admin(client)

        challenge_id = login_challenged(client, first_email)
        response = client.post(
            VERIFY_PATH,
            json={"challenge_id": challenge_id, "code": login_totp(first_secret)},
        )
        assert response.status_code == 204
        access = client.cookies.get(ACCESS_COOKIE)
        assert access is not None

    assert decode_access_token(access).user_id == first_user.id


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_recovery_code_completes_the_login_exactly_once(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)

        first = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )
        reused = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )

    assert first.status_code == 204
    assert reused.status_code == 401
    assert reused.json()["code"] == "MFA_INVALID"

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    used = (
        await db_session.scalars(
            select(MfaRecoveryCodeModel).where(
                MfaRecoveryCodeModel.mfa_credential_id == credential.id,
                MfaRecoveryCodeModel.used_at.is_not(None),
            )
        )
    ).all()
    assert len(used) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_recovery_code_is_accepted_in_any_reasonable_format(
    db_session: AsyncSession,
) -> None:
    """Codes get read off paper. Case and dashes must not decide the outcome."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)

        response = client.post(
            VERIFY_PATH,
            json={
                "challenge_id": login_challenged(client, email),
                "recovery_code": codes[0].lower().replace("-", " "),
            },
        )

    assert response.status_code == 204


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_recovery_use_is_audited_without_recording_the_code(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)
        response = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )
        assert response.status_code == 204

    entries = (
        await db_session.scalars(
            select(AuditLogModel).where(AuditLogModel.actor_user_id == user.id)
        )
    ).all()
    actions = {entry.action for entry in entries}

    assert "mfa.enrollment_started" in actions
    assert "mfa.enabled" in actions
    assert "mfa.recovery_code_used" in actions
    # The completed login is audited exactly as any other login is.
    assert "user.logged_in" in actions

    recovery_entry = next(entry for entry in entries if entry.action == "mfa.recovery_code_used")
    assert recovery_entry.entity_type == "MfaCredential"
    assert recovery_entry.after_data == {"remaining_recovery_codes": 9}

    # Nothing sensitive anywhere in the audit trail.
    serialised = "".join(
        f"{entry.action}{entry.before_data}{entry.after_data}" for entry in entries
    )
    for code in codes:
        assert code not in serialised
        assert code.replace("-", "") not in serialised
    assert PASSWORD not in serialised


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_regeneration_invalidates_the_previous_unused_set(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        _, original = enrol_admin(client)

        # Enrollment confirmation already made this session MFA-complete.
        regenerated = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )
        assert regenerated.status_code == 200
        fresh = list(regenerated.json()["recovery_codes"])

        old_code = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": original[0]},
        )
        new_code = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": fresh[0]},
        )

    assert set(original).isdisjoint(fresh)
    assert old_code.status_code == 401
    assert old_code.json()["code"] == "MFA_INVALID"
    assert new_code.status_code == 204


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_regeneration_is_audited_and_requires_the_password(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        wrong = client.post(
            REGENERATE_PATH,
            json={"current_password": "not-the-password"},
            headers=csrf_headers(client),
        )
        ok = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert wrong.status_code == 401
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"
    assert ok.status_code == 200

    entry = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.actor_user_id == user.id,
            AuditLogModel.action == "mfa.recovery_codes_regenerated",
        )
    )
    assert entry is not None
    assert entry.before_data == {"unused_codes_invalidated": 10}
    assert entry.after_data == {"recovery_codes_issued": 10}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_used_recovery_code_survives_regeneration_and_stays_unusable(
    db_session: AsyncSession,
) -> None:
    """Spent codes are kept, not deleted. `code_hash` is UNIQUE table-wide, so
    forgetting that a code was redeemed would let the same string be reissued
    and accepted a second time."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        _, codes = enrol_admin(client)

        spend = client.post(
            VERIFY_PATH,
            json={"challenge_id": login_challenged(client, email), "recovery_code": codes[0]},
        )
        assert spend.status_code == 204

        client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    credential = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == user.id)
    )
    assert credential is not None
    rows = (
        await db_session.scalars(
            select(MfaRecoveryCodeModel).where(
                MfaRecoveryCodeModel.mfa_credential_id == credential.id
            )
        )
    ).all()

    # 9 unused wiped, 1 spent retained, 10 fresh issued.
    assert len([row for row in rows if row.used_at is not None]) == 1
    assert len([row for row in rows if row.used_at is None]) == 10


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_mfa_claim_survives_a_refresh(db_session: AsyncSession) -> None:
    """Rotation re-mints the access token, so without carrying the claim an
    administrator would drop back to MFA-incomplete every 15 minutes."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        challenge_id = login_challenged(client, email)
        assert (
            client.post(
                VERIFY_PATH,
                json={"challenge_id": challenge_id, "code": login_totp(secret)},
            ).status_code
            == 204
        )

        refreshed = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert refreshed.status_code == 204

        still_allowed = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )
        rotated = client.cookies.get(ACCESS_COOKIE)

    assert still_allowed.status_code == 200
    assert rotated is not None
    assert decode_access_token(rotated).mfa_completed is True


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_a_confirmed_credential_logs_in_normally(
    db_session: AsyncSession,
) -> None:
    """No enabled credential means nothing to challenge. Anything else would be
    an enrollment deadlock: the endpoints that fix it need the very session the
    challenge would be withholding."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        client.cookies.clear()
        response = client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD})

        assert response.status_code == 200
        assert client.cookies.get(ACCESS_COOKIE) is not None
        # ...but the admin boundary is still shut until MFA is actually done.
        blocked = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert blocked.status_code == 401
    assert blocked.json()["code"] == "MFA_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_started_but_unconfirmed_enrollment_does_not_challenge_login(
    db_session: AsyncSession,
) -> None:
    """`enabled_at IS NULL` is an in-progress enrollment, not a second factor."""
    from app.main import app
    from tests.integration.identity.test_mfa_enrollment import start_enrollment

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        start_enrollment(client)

        client.cookies.clear()
        response = client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD})

    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_login_is_untouched_by_mfa(db_session: AsyncSession) -> None:
    """VS-003's behaviour for ordinary customers must be exactly as it was."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        client.cookies.clear()
        response = client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD})

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == email
        assert body["role"] == "customer"
        assert client.cookies.get(ACCESS_COOKIE) is not None
        assert client.cookies.get(REFRESH_COOKIE) is not None
        assert client.cookies.get(CSRF_COOKIE) is not None

        # And a customer still cannot see the admin-only MFA routes.
        regenerate = client.post(
            REGENERATE_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert regenerate.status_code == 404
    assert regenerate.json()["code"] == "NOT_FOUND"
