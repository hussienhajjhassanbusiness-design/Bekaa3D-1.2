"""The IP-hash salt and pepper never reach logs, audit rows or errors (VS-046, ADR-028).

Logs are captured through the application's own formatter, as test_ensure_partitions does."""

import base64
import io
import logging
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs import rotate_ip_salt as rotate_module
from app.jobs.rotate_ip_salt import IpHashSaltRotationError, rotate_ip_salt
from tests.integration.platform.test_rotate_ip_salt import make_due


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    return buffer


def _forms(secret: bytes) -> list[str]:
    return [secret.hex(), secret.hex().upper(), base64.b64encode(secret).decode(), repr(secret)]


async def _all_salts(engine: AsyncEngine) -> list[bytes]:
    async with engine.connect() as conn:
        return [bytes(r.salt) for r in await conn.execute(text("SELECT salt FROM ip_hash_salts"))]


async def _rotation_audit_text(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT coalesce(before_data::text, '') "
                "|| coalesce(after_data::text, '') AS payload "
                "FROM audit_logs WHERE action = 'ip_hash_salt.rotated'"
            )
        )
        return " ".join(str(r.payload) for r in rows)


@pytest.mark.integration
async def test_a_rotation_logs_and_audits_ids_but_never_salt_bytes_or_pepper(
    db_engine: AsyncEngine, captured_logs: io.StringIO
) -> None:
    [old_salt] = await _all_salts(db_engine)
    await make_due(db_engine)
    assert await rotate_ip_salt({"session_factory": async_sessionmaker(db_engine)}) is True
    [new_salt] = await _all_salts(db_engine)

    logs = captured_logs.getvalue()
    assert "ip_hash_salt_rotated" in logs
    stored = await _rotation_audit_text(db_engine)
    pepper = get_settings().ip_hash_salt.get_secret_value()
    for haystack in (logs, stored):
        assert pepper not in haystack
        for form in _forms(old_salt) + _forms(new_salt):
            assert form not in haystack


class _ClosedConnectionStore:
    """Fails the way a dropped connection does, after the salt has been read."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def lock_rotation(self) -> None:
        raise ConnectionResetError("connection closed while holding salt 00ff")

    async def current_created_at(self) -> None:
        raise AssertionError("unreachable")


@pytest.mark.integration
async def test_a_database_error_logs_and_raises_the_class_only(
    db_engine: AsyncEngine, captured_logs: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotate_module, "ip_hash_salt_store", _ClosedConnectionStore)
    with pytest.raises(IpHashSaltRotationError) as raised:
        await rotate_ip_salt({"session_factory": async_sessionmaker(db_engine)})

    assert str(raised.value) == "ConnectionResetError"
    assert raised.value.__cause__ is None
    logs = captured_logs.getvalue()
    assert "ip_hash_salt_rotation_failed" in logs and "ConnectionResetError" in logs
    assert "connection closed while holding salt" not in logs
