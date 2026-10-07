import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings

_FAKE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "JWT_SIGNING_KEY": "test-jwt-signing-key",
    "CSRF_SECRET": "test-csrf-secret",
    "IP_HASH_SALT": "test-ip-hash-salt",
}


@pytest.fixture
def client() -> Generator[TestClient]:
    """A client whose DB/Redis settings point at nothing listening on localhost,
    so dependency-touching endpoints fail fast without needing real infrastructure."""
    previous = {key: os.environ.get(key) for key in _FAKE_ENV}
    os.environ.update(_FAKE_ENV)
    get_settings.cache_clear()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_liveness_does_not_probe_dependencies(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_when_database_unavailable(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["status"] == 503
    assert "request_id" in body


def test_request_id_header_present_on_every_response(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers["X-Request-ID"].startswith("req_")


def test_incoming_request_id_is_echoed_back(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "req_caller_supplied"})
    assert response.headers["X-Request-ID"] == "req_caller_supplied"


def test_not_found_returns_rfc9457_problem_shape(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["status"] == 404
    assert body["instance"] == "/does-not-exist"
    assert "request_id" in body
    assert body["errors"] == []
