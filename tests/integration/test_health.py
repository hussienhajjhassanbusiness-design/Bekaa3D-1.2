import pytest
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.config import get_settings


@pytest.mark.integration
def test_readiness_reports_ok_when_db_and_redis_are_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        PostgresContainer("postgres:16", driver="asyncpg") as postgres,
        RedisContainer("redis:7-alpine") as redis_server,
    ):
        # monkeypatch, not os.environ: both values must be restored afterwards,
        # or every later test that builds Settings inherits dead containers.
        monkeypatch.setenv("DATABASE_URL", postgres.get_connection_url())
        monkeypatch.setenv(
            "REDIS_URL",
            f"redis://{redis_server.get_container_host_ip()}:"
            f"{redis_server.get_exposed_port(6379)}/0",
        )
        get_settings.cache_clear()

        from app.main import app

        with TestClient(app) as client:
            response = client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "commit" in body

        get_settings.cache_clear()


@pytest.mark.integration
def test_readiness_fails_when_redis_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Readiness probes Redis as well as Postgres, and the suite only ever
    covered the database leg. With a healthy database behind it, a dead Redis
    must still take the instance out of rotation - otherwise a load balancer
    keeps sending traffic to a process that cannot rate-limit, throttle logins
    or enqueue a job.

    The `detail` assertion is what proves the request reached the Redis check
    rather than failing earlier for some unrelated reason.
    """
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        monkeypatch.setenv("DATABASE_URL", postgres.get_connection_url())
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        get_settings.cache_clear()

        from app.main import app

        with TestClient(app) as client:
            response = client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert body["detail"] == "Redis is unavailable."

        # Previously `os.environ.pop("REDIS_URL")`, which deleted the variable
        # outright rather than restoring it; without a .env file every later
        # test that built Settings then failed with `redis_url Field required`.
        get_settings.cache_clear()
