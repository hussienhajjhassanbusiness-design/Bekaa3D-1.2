"""The worker container's health probe (app.worker_health).

Regression: the compose healthcheck ran `arq app.worker.WorkerSettings --check`, which
imports the whole app. Over the ./src bind mount on a Windows host that took 16-30 s
against a 10 s timeout, so a working worker was always reported unhealthy. The probe must
stay import-light and check the same Redis the worker uses."""

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; no new dependency for one test

from app import worker, worker_health
from app.core.config import get_settings

SRC = Path(worker_health.__file__)
COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _top_level_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_the_probe_imports_only_arq_and_the_standard_library() -> None:
    assert _top_level_imports(SRC) == {"asyncio", "os", "sys", "arq"}


def test_the_probe_checks_the_same_redis_as_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://:s3cret@cache.internal:6380/4")
    get_settings.cache_clear()
    try:
        probe = worker_health.redis_settings()
        used = worker._redis_settings()
    finally:
        get_settings.cache_clear()
    assert (probe.host, probe.port, probe.database) == ("cache.internal", 6380, 4)
    assert (probe.host, probe.port, probe.database, probe.password, probe.ssl) == (
        used.host,
        used.port,
        used.database,
        used.password,
        used.ssl,
    )


@pytest.mark.parametrize(("heartbeat", "expected"), [(b"Nov-26 j_complete=1", 0), (None, 1)])
def test_the_exit_code_follows_the_heartbeat(
    monkeypatch: pytest.MonkeyPatch, heartbeat: bytes | None, expected: int
) -> None:
    asked: list[str] = []

    class FakeRedis:
        async def get(self, key: str) -> bytes | None:
            asked.append(key)
            return heartbeat

        async def close(self, close_connection_pool: bool = False) -> None:
            return None

    async def fake_pool(settings: Any) -> FakeRedis:
        return FakeRedis()

    monkeypatch.setattr("arq.worker.create_pool", fake_pool)
    assert worker_health.main() == expected
    assert asked == ["arq:queue:health-check"]  # arq's default queue, which the worker uses


def test_compose_runs_this_probe_for_the_worker() -> None:
    services: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    check = services["worker"]["healthcheck"]
    assert check["test"] == ["CMD", "python", "-m", "app.worker_health"]
