"""The `/api/v1/admin` boundary: authenticated, administrator, MFA complete.

VS-005 ships the boundary without concrete admin endpoints - those belong to
VS-007 and VS-009. To test the prefix itself rather than only the routes that
happen to use `require_admin` today, these tests mount a probe route on a router
configured exactly as `app.api.v1.admin` is."""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestIDMiddleware
from app.api.v1.router import router as v1_router
from app.identity.api.dependencies import require_admin
from app.identity.application.security.session_tokens import AccessTokenClaims
from app.main import lifespan
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import (
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

PROBE_PATH = "/api/v1/admin/probe"


def app_with_probe() -> FastAPI:
    """Mirror src/app/main.py, plus one route behind the admin boundary.

    The probe router is declared the same way `app.api.v1.admin` declares its:
    `require_admin` as a router-level dependency, so what is under test is the
    boundary rather than a per-route check."""
    probe_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

    @probe_router.get("/probe")
    async def _probe(claims: AccessTokenClaims = Depends(require_admin)) -> dict[str, str]:
        return {"user_id": str(claims.user_id)}

    versioned = APIRouter(prefix="/api/v1")
    versioned.include_router(probe_router)

    app = FastAPI(title="Bekaa3D API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    # Before v1_router: its admin catch-all (VS-011) answers every /api/v1/admin
    # path no earlier route serves. Real admin routes live inside that router.
    app.include_router(versioned)
    app.include_router(v1_router)
    return app


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_unauthenticated_caller_is_told_to_authenticate() -> None:
    """No session at all is the one case where 401 is correct: there is nothing
    to hide yet, and the client genuinely needs to log in."""
    with TestClient(app_with_probe()) as client:
        response = client.get(PROBE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_authenticated_customer_gets_404_not_403(db_session: AsyncSession) -> None:
    """SEC-10. A 403 would confirm the route exists and tell an ordinary
    customer exactly which admin surface to probe."""
    email = unique_email()
    with TestClient(app_with_probe()) as client:
        await register_and_verify(client, db_session, email)
        login(client, email)
        response = client.get(PROBE_PATH)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_cannot_distinguish_a_real_admin_route_from_a_missing_one(
    db_session: AsyncSession,
) -> None:
    """The whole point of the information-hiding rule: both answers identical."""
    email = unique_email()
    with TestClient(app_with_probe()) as client:
        await register_and_verify(client, db_session, email)
        login(client, email)
        real = client.get(PROBE_PATH)
        imaginary = client.get("/api/v1/admin/does-not-exist")

    assert real.status_code == imaginary.status_code == 404
    assert real.json()["code"] == imaginary.json()["code"] == "NOT_FOUND"
    assert real.json()["detail"] == imaginary.json()["detail"]
    assert real.json()["title"] == imaginary.json()["title"]
    assert real.json()["type"] == imaginary.json()["type"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_completed_mfa_is_refused(db_session: AsyncSession) -> None:
    """An administrator mid-enrollment holds a real session, and the boundary
    still refuses it (api-endpoints.md:105)."""
    email = unique_email()
    with TestClient(app_with_probe()) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.get(PROBE_PATH)

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "MFA_REQUIRED"
    # No challenge is minted here. Under the login-gated flow the only source
    # of a challenge is POST /auth/login, so the boundary must not offer a
    # second, session-bound route to an MFA-complete session.
    assert "challenge_id" not in body


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_who_completed_the_login_challenge_is_allowed_through(
    db_session: AsyncSession,
) -> None:
    email = unique_email()
    with TestClient(app_with_probe()) as client:
        user = await make_admin(client, db_session, email)
        login(client, email)
        secret, _ = enrol_admin(client)

        # Fresh login, so the challenge is exercised rather than inherited from
        # enrollment confirmation.
        challenge_id = login_challenged(client, email)
        blocked = client.get(PROBE_PATH)

        verified = client.post(
            "/api/v1/auth/mfa/verify",
            json={"challenge_id": challenge_id, "code": login_totp(secret)},
        )
        allowed = client.get(PROBE_PATH)

    # Before verifying there is no session at all, so the boundary answers with
    # the unauthenticated error rather than the MFA one.
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_REQUIRED"
    assert verified.status_code == 204
    assert allowed.status_code == 200
    assert allowed.json()["user_id"] == str(user.id)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_enrolling_an_admin_does_not_by_itself_open_the_boundary_for_other_clients(
    db_session: AsyncSession,
) -> None:
    """MFA completion is session state, not account state. Once MFA is enabled,
    a second client cannot even obtain a session without clearing the factor -
    its login is challenged rather than granted."""
    email = unique_email()
    with TestClient(app_with_probe()) as first, TestClient(app_with_probe()) as second:
        await make_admin(first, db_session, email)
        login(first, email)
        enrol_admin(first)

        challenged = second.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        response = second.get(PROBE_PATH)

    assert challenged.status_code == 202
    assert second.cookies.get("access_token") is None
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_forged_mfa_claim_cannot_be_smuggled_in(db_session: AsyncSession) -> None:
    """The claim lives inside a signed JWT, so tampering invalidates the whole
    token rather than granting admin."""
    email = unique_email()
    with TestClient(app_with_probe()) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        client.cookies.set("access_token", "forged.mfa.token")
        response = client.get(PROBE_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
