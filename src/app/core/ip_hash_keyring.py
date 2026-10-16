"""Keeps the in-process IP-hash key in step with `ip_hash_salts` (VS-046, ADR-028).

Single-flight is an attempt-timestamp guard, not an asyncio.Lock: no lock bound to
one event loop, and with no key loaded the database is still asked at most once a minute."""

import threading
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import clear_ip_hash_key, install_ip_hash_key, ip_hash_key_loaded_at
from app.platform.public import current_ip_hash_salt

logger = structlog.get_logger()

REFRESH_SECONDS = 60.0

_attempt_guard = threading.Lock()  # held for a comparison only, never across an await
_next_attempt_at = float("-inf")


def monotonic() -> float:
    """The keyring's clock; tests patch this to move time forward."""
    return time.monotonic()


def refresh_due(now: float) -> bool:
    loaded_at = ip_hash_key_loaded_at()
    return loaded_at is None or now - loaded_at >= REFRESH_SECONDS


def claim_refresh_attempt(now: float) -> bool:
    """True for at most one caller per REFRESH_SECONDS, across threads and event loops."""
    global _next_attempt_at
    with _attempt_guard:
        if now < _next_attempt_at:
            return False
        _next_attempt_at = now + REFRESH_SECONDS
        return True


async def refresh_ip_hash_key(
    session_factory: async_sessionmaker[AsyncSession], *, now: float | None = None
) -> bool:
    """Reload the current salt. On any failure keep the old key and log the error class only."""
    moment = monotonic() if now is None else now
    try:
        async with session_factory() as session:
            salt = await current_ip_hash_salt(session)
    except Exception as exc:  # a refresh must never fail the request that triggered it
        await logger.awarning("ip_hash_key_refresh_failed", error=type(exc).__name__)
        return False
    if salt is None:
        await logger.awarning("ip_hash_key_missing")
        return False
    install_ip_hash_key(salt_id=salt.id, salt=salt.salt, now=moment)
    return True


async def maybe_refresh_ip_hash_key(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Refresh when the key is stale or missing and this caller wins the attempt slot."""
    now = monotonic()
    if refresh_due(now) and claim_refresh_attempt(now):
        await refresh_ip_hash_key(session_factory, now=now)


def reset_ip_hash_keyring() -> None:
    """Forget the key and the attempt guard (tests only)."""
    global _next_attempt_at
    clear_ip_hash_key()
    with _attempt_guard:
        _next_attempt_at = float("-inf")
