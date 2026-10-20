"""PHONE_HASH_SALT never reaches logs, responses, errors or the database (VS-028 PR A,
ADR-024 d6). Logs are captured through the application's own formatter."""

import io
import logging
from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import ConfigurationError, hash_phone

SALT = "phone-salt-sentinel-7f3a9c1e5b2d4f6a8c0e"


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    return buffer


@pytest.fixture
def salt(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("PHONE_HASH_SALT", SALT)
    get_settings.cache_clear()
    yield SALT
    get_settings.cache_clear()


def test_the_settings_object_never_prints_the_salt(salt: str) -> None:
    settings = get_settings()
    assert salt not in repr(settings)
    assert salt not in str(settings.model_dump())
    assert salt not in settings.model_dump_json()


def test_a_logged_salt_or_settings_dump_is_redacted(salt: str, captured_logs: io.StringIO) -> None:
    log = structlog.get_logger("leak-probe")
    log.info("probe_phone_hash_salt", phone_hash_salt=salt, nested={"salt": salt})
    log.info("probe_settings", settings=get_settings().model_dump())
    logs = captured_logs.getvalue()
    assert "probe_phone_hash_salt" in logs and "probe_settings" in logs
    assert salt not in logs


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_refused_boot_names_the_setting_but_never_its_value(
    monkeypatch: pytest.MonkeyPatch, captured_logs: io.StringIO
) -> None:
    from app.main import lifespan

    weak = "generate_with__" + "s" * 20
    monkeypatch.setenv("CAPTCHA_PROVIDER", "turnstile")
    monkeypatch.setenv("TURNSTILE_SECRET", "test-only")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    monkeypatch.setenv("PHONE_HASH_SALT", weak)
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError) as raised:
            async with lifespan(FastAPI()):
                pass
    finally:
        get_settings.cache_clear()
    assert "PHONE_HASH_SALT" in str(raised.value)
    assert weak not in str(raised.value)
    assert weak not in captured_logs.getvalue()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_requests_and_a_hash_leave_the_salt_out_of_responses_and_the_database(
    salt: str, db_engine: AsyncEngine, captured_logs: io.StringIO
) -> None:
    from app.main import app

    digest = hash_phone("+96171999888")
    with TestClient(app) as client:
        bodies = [
            client.get("/api/v1/settings/public"),
            client.get("/health/live"),
            client.get("/api/v1/does-not-exist"),
        ]
    for response in bodies:
        assert salt not in response.text
        assert all(salt not in value for value in response.headers.values())
    assert salt not in captured_logs.getvalue()
    assert salt not in digest

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables: list[str] = list(result.scalars())
        assert "cash_payment_blocks" in tables
        for table in tables:
            hit = await conn.scalar(
                text(f'SELECT count(*) FROM "{table}" t WHERE t::text LIKE :needle'),
                {"needle": f"%{salt}%"},
            )
            assert hit == 0, table
