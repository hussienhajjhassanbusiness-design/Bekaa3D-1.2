"""The generated OpenAPI document describes the real security requirements.

VS-005 deliverable (vertical-slice-plan.md:128). These are cheap assertions,
but the schema is generated code that nothing else exercises - without them a
typo in a path constant would silently ship a document claiming that
`/auth/login` needs a session cookie, or that the admin boundary needs nothing.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.cookies import ACCESS_COOKIE
from app.identity.api.dependencies import CSRF_HEADER

SCHEMA_PATH = "/openapi.json"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_schema_declares_the_cookie_and_csrf_schemes() -> None:
    from app.main import app

    with TestClient(app) as client:
        schema = client.get(SCHEMA_PATH).json()

    schemes = schema["components"]["securitySchemes"]
    assert schemes["sessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": ACCESS_COOKIE,
        "description": schemes["sessionCookie"]["description"],
    }
    assert schemes["csrfToken"]["in"] == "header"
    assert schemes["csrfToken"]["name"] == CSRF_HEADER


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_public_and_challenge_authenticated_routes_require_no_session() -> None:
    """`/auth/login` cannot require a session - it is how you get one. Nor can
    `/auth/mfa/verify`, which runs before any session exists."""
    from app.main import app

    with TestClient(app) as client:
        paths = client.get(SCHEMA_PATH).json()["paths"]

    assert "security" not in paths["/api/v1/auth/login"]["post"]
    assert "security" not in paths["/api/v1/auth/mfa/verify"]["post"]
    assert "security" not in paths["/api/v1/auth/register"]["post"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_authenticated_unsafe_methods_require_both_the_cookie_and_csrf() -> None:
    from app.main import app

    with TestClient(app) as client:
        paths = client.get(SCHEMA_PATH).json()["paths"]

    for path in ("/api/v1/auth/mfa/setup", "/api/v1/auth/mfa/recovery-codes/regenerate"):
        security = paths[path]["post"]["security"]
        assert security == [{"sessionCookie": [], "csrfToken": []}], path


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_login_route_documents_both_of_its_success_shapes() -> None:
    """200 SessionRead and 202 MfaChallengeRead are both real outcomes, and a
    client that only handles the first will break on its first admin login."""
    from app.main import app

    with TestClient(app) as client:
        responses = client.get(SCHEMA_PATH).json()["paths"]["/api/v1/auth/login"]["post"][
            "responses"
        ]

    assert "200" in responses
    assert "202" in responses
    assert (
        responses["202"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MfaChallengeRead"
    )
