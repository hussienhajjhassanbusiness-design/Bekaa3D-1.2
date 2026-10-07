"""MFA endpoints carry their own, much tighter rate-limit policy.

A TOTP is six digits, so the entire keyspace is a million guesses. The limit -
not the length of the secret - is what makes online guessing hopeless, which is
why these ceilings are far below the customer auth limits in VS-002."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import (
    SETUP_PATH,
    csrf_headers,
    enrol_admin,
    login,
    make_admin,
    unique_email,
)

VERIFY_PATH = "/api/v1/auth/mfa/verify"
REGENERATE_PATH = "/api/v1/auth/mfa/recovery-codes/regenerate"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_enrollment_is_capped_well_below_the_customer_auth_limits(
    db_session: AsyncSession,
) -> None:
    """5 per hour. An administrator enrols roughly once, ever."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)

        statuses = [
            client.post(
                SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
            ).status_code
            for _ in range(6)
        ]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_limit_response_carries_the_standard_headers(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        for _ in range(5):
            client.post(
                SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
            )
        limited = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
        )

    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert limited.headers["RateLimit-Limit"] == "5"
    assert limited.headers["RateLimit-Remaining"] == "0"
    assert int(limited.headers["RateLimit-Reset"]) > 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_repeated_wrong_codes_are_throttled_before_the_keyspace_is_dented(
    db_session: AsyncSession,
) -> None:
    """10 attempts per 15 minutes against a million codes."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        # No session and no CSRF header: /verify is reached before either
        # exists, so the rate limiter is the only thing standing in front of
        # the six-digit keyspace.
        client.cookies.clear()
        statuses = []
        for _ in range(11):
            response = client.post(
                VERIFY_PATH,
                json={"challenge_id": "irrelevant", "code": "000000"},
            )
            statuses.append(response.status_code)

    # The first ten are answered on their merits (410 - the challenge is bogus),
    # and the eleventh never reaches the handler at all.
    assert statuses[:10] == [410] * 10
    assert statuses[10] == 429


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_mfa_limits_are_separate_from_the_customer_login_limit(
    db_session: AsyncSession,
) -> None:
    """Exhausting the MFA enrollment bucket must not lock out ordinary login,
    and vice versa - they are different keys on different policies."""
    from app.main import app

    admin_email = unique_email()
    customer_email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, admin_email)
        await register_and_verify(client, db_session, customer_email)
        login(client, admin_email)

        for _ in range(6):
            client.post(
                SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf_headers(client)
            )

        customer_login = client.post(
            "/api/v1/auth/login", json={"email": customer_email, "password": PASSWORD}
        )

    assert customer_login.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_recovery_regeneration_is_capped(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        enrol_admin(client)

        statuses = [
            client.post(
                REGENERATE_PATH,
                json={"current_password": PASSWORD},
                headers=csrf_headers(client),
            ).status_code
            for _ in range(6)
        ]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
