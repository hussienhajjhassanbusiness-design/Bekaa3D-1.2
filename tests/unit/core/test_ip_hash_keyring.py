"""The IP-hash keyring's refresh and throttle (VS-046 amendments B and C).

A fake session factory stands in for PostgreSQL: these tests count attempts."""

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.core import ip_hash_keyring as keyring
from app.core.security import clear_ip_hash_key, hash_ip, ip_hash_key_loaded_at
from app.platform.public import IpHashSalt


class _FakeFactory:
    """Counts sessions opened; `current_ip_hash_salt` is patched to read `self.salt`."""

    def __init__(self, salt: IpHashSalt | None = None, error: Exception | None = None) -> None:
        self.salt = salt
        self.error = error
        self.calls = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator["_FakeFactory"]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        yield self


@pytest.fixture(autouse=True)
def fake_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    async def read(session: Any) -> IpHashSalt | None:
        salt: IpHashSalt | None = session.salt
        return salt

    monkeypatch.setattr(keyring, "current_ip_hash_salt", read)
    keyring.reset_ip_hash_keyring()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1_000.0]
    monkeypatch.setattr(keyring, "monotonic", lambda: now[0])
    return now


def _salt(fill: int) -> IpHashSalt:
    return IpHashSalt(id=uuid4(), created_at=datetime.now(UTC), salt=bytes([fill]) * 32)


async def test_a_refresh_installs_the_current_salt() -> None:
    factory = _FakeFactory(_salt(7))
    assert await keyring.refresh_ip_hash_key(factory, now=5.0) is True  # type: ignore[arg-type]
    assert ip_hash_key_loaded_at() == 5.0
    assert hash_ip("192.0.2.1") is not None


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def awarning(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


async def test_a_failed_refresh_keeps_the_previous_key_and_logs_the_class_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _RecordingLogger()
    monkeypatch.setattr(keyring, "logger", recorder)
    before = hash_ip("192.0.2.1")
    factory = _FakeFactory(error=ConnectionRefusedError("secret-in-message"))
    assert await keyring.refresh_ip_hash_key(factory) is False  # type: ignore[arg-type]
    assert hash_ip("192.0.2.1") == before
    assert recorder.events == [("ip_hash_key_refresh_failed", {"error": "ConnectionRefusedError"})]


async def test_a_missing_salt_row_keeps_the_previous_key() -> None:
    before = hash_ip("192.0.2.1")
    assert await keyring.refresh_ip_hash_key(_FakeFactory(None)) is False  # type: ignore[arg-type]
    assert hash_ip("192.0.2.1") == before


async def test_a_fresh_key_is_not_refreshed(clock: list[float]) -> None:
    factory = _FakeFactory(_salt(1))
    await keyring.refresh_ip_hash_key(factory, now=clock[0])  # type: ignore[arg-type]
    clock[0] += keyring.REFRESH_SECONDS - 1
    await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
    assert factory.calls == 1


async def test_a_stale_key_is_refreshed_once_per_interval(clock: list[float]) -> None:
    factory = _FakeFactory(_salt(1))
    await keyring.refresh_ip_hash_key(factory, now=clock[0])  # type: ignore[arg-type]
    before = hash_ip("192.0.2.1")
    factory.salt = _salt(2)
    clock[0] += keyring.REFRESH_SECONDS
    await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
    assert factory.calls == 2
    assert hash_ip("192.0.2.1") != before


async def test_with_no_key_the_middleware_path_refreshes(clock: list[float]) -> None:
    """Amendment B: a missing key is itself a reason to refresh."""
    clear_ip_hash_key()
    factory = _FakeFactory(_salt(3))
    await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
    assert factory.calls == 1
    assert hash_ip("192.0.2.1") is not None


async def test_with_no_salt_row_attempts_are_throttled_to_one_per_interval(
    clock: list[float],
) -> None:
    """Amendment B: a missing row cannot turn every request into a database read."""
    clear_ip_hash_key()
    factory = _FakeFactory(None)
    for _ in range(50):
        await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
        clock[0] += 0.5
    assert factory.calls == 1
    clock[0] += keyring.REFRESH_SECONDS
    await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
    assert factory.calls == 2
    assert hash_ip("192.0.2.1") is None


async def test_a_database_outage_with_no_key_is_throttled_too(clock: list[float]) -> None:
    clear_ip_hash_key()
    factory = _FakeFactory(error=OSError("down"))
    for _ in range(10):
        await keyring.maybe_refresh_ip_hash_key(factory)  # type: ignore[arg-type]
    assert factory.calls == 1


async def test_concurrent_requests_on_one_loop_trigger_one_refresh(clock: list[float]) -> None:
    clear_ip_hash_key()
    factory = _FakeFactory(_salt(4))
    await asyncio.gather(*(keyring.maybe_refresh_ip_hash_key(factory) for _ in range(20)))  # type: ignore[arg-type]
    assert factory.calls == 1


def test_the_guard_works_across_event_loops_and_threads(clock: list[float]) -> None:
    """Amendment C: each TestClient runs its own loop; no lock may be bound to one."""
    clear_ip_hash_key()
    factory = _FakeFactory(None)
    barrier = threading.Barrier(8)

    def run() -> None:
        barrier.wait()
        asyncio.run(keyring.maybe_refresh_ip_hash_key(factory))  # type: ignore[arg-type]

    threads = [threading.Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert factory.calls == 1


def test_the_keyring_creates_no_asyncio_primitive_at_import() -> None:
    """Amendment C: nothing at module level may be bound to an event loop."""
    for value in vars(keyring).values():
        assert not isinstance(value, asyncio.Lock | asyncio.Event | asyncio.Semaphore)


def test_reset_clears_the_key_and_the_guard() -> None:
    assert keyring.claim_refresh_attempt(10.0) is True
    assert keyring.claim_refresh_attempt(10.0) is False
    keyring.reset_ip_hash_keyring()
    assert ip_hash_key_loaded_at() is None
    assert keyring.claim_refresh_attempt(10.0) is True
