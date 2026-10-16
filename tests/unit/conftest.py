"""Unit tests run without any environment or `.env` file.

Several units read `get_settings()` - the token signer, the CSRF derivation, the
secret cipher, the error handlers - and `Settings` has required fields. Unit
tests used to pass only when something else (an integration fixture that ran
first, or a local `.env`) had already provided them, so `pytest tests/unit` on
its own failed. Every required setting gets a placeholder here unless the
environment already sets it; none of them is ever used to reach a real service.
"""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest

from app.core.config import get_settings
from app.core.ip_hash_keyring import reset_ip_hash_keyring
from app.core.security import install_ip_hash_key

# Dead ports: a unit test that accidentally touches the network fails fast
# instead of reaching a real database or Redis.
_PLACEHOLDER_SETTINGS = {
    "DATABASE_URL": "postgresql+asyncpg://unit:unit@127.0.0.1:1/unit",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "JWT_SIGNING_KEY": "unit-test-jwt-signing-key-of-at-least-32-bytes",
    "CSRF_SECRET": "unit-test-csrf-secret",
    "IP_HASH_SALT": "unit-test-ip-hash-salt",
    "MFA_SECRET_KEY": "unit-test-mfa-secret-key",
}


@pytest.fixture(autouse=True)
def placeholder_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name, value in _PLACEHOLDER_SETTINGS.items():
        if name not in os.environ:
            monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    # Settings read under the placeholders must not outlive the test.
    get_settings.cache_clear()


@contextmanager
def installed_ip_hash_test_key() -> Iterator[None]:
    """A known IP-hash key for the duration; then the key is None and the guard reset."""
    install_ip_hash_key(salt_id=UUID(int=1), salt=b"\x01" * 32, now=time.monotonic())
    try:
        yield
    finally:
        reset_ip_hash_keyring()


@pytest.fixture(autouse=True)
def ip_hash_test_key(placeholder_settings: None) -> Iterator[None]:
    """Every unit test runs with the known key (VS-046, amendment G)."""
    with installed_ip_hash_test_key():
        yield
