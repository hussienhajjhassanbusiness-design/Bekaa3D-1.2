"""End-to-end checks on the cross-cutting error contract (VS-001).

These go through a real TestClient rather than calling the handlers directly,
because the three bugs they guard were all in the *interaction* between
Starlette's machinery and our handlers - a handler-level test would have passed
while the served response was still wrong.
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS

_FAKE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "JWT_SIGNING_KEY": "test-jwt-signing-key",
    "CSRF_SECRET": "test-csrf-secret",
    "IP_HASH_SALT": "test-ip-hash-salt",
}

REGISTER_PATH = "/api/v1/auth/register"


@pytest.fixture
def client() -> Generator[TestClient]:
    """Points DB and Redis at dead localhost ports, so any route that touches a
    dependency raises and exercises the unhandled-exception path.

    `raise_server_exceptions=False` is what makes the 500 tests possible: the
    default re-raises into the test instead of letting the response be built.
    Deliberately kept separate from test_health.py's client, which keeps the
    default so a genuine crash there still surfaces as a test error.
    """
    previous = {key: os.environ.get(key) for key in _FAKE_ENV}
    os.environ.update(_FAKE_ENV)
    get_settings.cache_clear()

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    get_settings.cache_clear()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_method_not_allowed_keeps_the_allow_header(client: TestClient) -> None:
    """RFC 9110 15.5.6 makes `Allow` mandatory on a 405, and Starlette supplies
    it on the HTTPException. Converting that exception into a problem document
    used to drop every header it carried."""
    response = client.post("/health/live")

    assert response.status_code == 405
    allowed = {method.strip() for method in response.headers["allow"].split(",")}
    assert "GET" in allowed
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_malformed_json_body_is_400_malformed_request(client: TestClient) -> None:
    """api-endpoints.md 5.1: a body that cannot be parsed is 400
    MALFORMED_REQUEST, not a field-validation failure."""
    response = client.post(
        REGISTER_PATH, content=b"{not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["status"] == 400


@pytest.fixture
def crashing_liveness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuinely unhandled exception, raised from a route that touches no
    dependency. A dead database or Redis used to be the trigger here, but an
    outage is now a handled 503 (BUG-15) and never reaches the
    ServerErrorMiddleware path these tests guard."""
    from app.api import health

    def boom() -> None:
        raise RuntimeError("unhandled")

    monkeypatch.setattr(health, "LivenessRead", boom)


@pytest.mark.usefixtures("crashing_liveness")
def test_unhandled_error_echoes_a_caller_supplied_request_id(client: TestClient) -> None:
    """The header and the body must agree. They did not: an unhandled exception
    is caught by ServerErrorMiddleware, which sits outside RequestIDMiddleware,
    so the response never passed back through the middleware that sets the
    header - leaving a caller with an ID in the body and nothing to match it
    against in the response they actually received."""
    response = client.get("/health/live", headers={"X-Request-ID": "req_caller_supplied_500"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req_caller_supplied_500"
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == "req_caller_supplied_500"


@pytest.mark.usefixtures("crashing_liveness")
def test_unhandled_error_returns_a_generated_request_id(client: TestClient) -> None:
    """Same guarantee when the caller supplies no ID: the generated one must
    reach the response header, not only the body."""
    response = client.get("/health/live")

    assert response.status_code == 500
    header_id = response.headers["X-Request-ID"]
    assert header_id.startswith("req_")
    assert response.json()["request_id"] == header_id


def test_a_dependency_outage_is_a_503_whose_request_id_matches(client: TestClient) -> None:
    """The dead database and Redis of the `client` fixture: BUG-15 answers 503
    SERVICE_UNAVAILABLE, and the correlation guarantee holds there too."""
    response = client.post(
        REGISTER_PATH,
        json={
            "captcha_token": FAKE_CAPTCHA_PASS,
            "email": "someone@example.com",
            "password": "a-valid-password",
        },
        headers={"X-Request-ID": "req_caller_supplied_503"},
    )

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "req_caller_supplied_503"
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["request_id"] == "req_caller_supplied_503"
