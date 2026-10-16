"""Keyed `hash_ip` (VS-046, SEC-25, ADR-028): HMAC under a pepper-and-salt key."""

import re
import time
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core import security
from app.core.config import get_settings
from app.core.security import clear_ip_hash_key, hash_ip, install_ip_hash_key

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PEPPER = "unit-test-ip-hash-salt"


def _install(salt: bytes) -> None:
    install_ip_hash_key(salt_id=UUID(int=2), salt=salt, now=time.monotonic())


def test_the_hash_is_64_lowercase_hex_and_deterministic_for_one_key() -> None:
    digest = hash_ip("203.0.113.7")
    assert digest is not None and HEX64.match(digest)
    assert hash_ip("203.0.113.7") == digest
    assert "203.0.113.7" not in digest


def test_a_different_salt_gives_a_different_hash() -> None:
    before = hash_ip("203.0.113.7")
    _install(b"\x02" * 32)
    assert hash_ip("203.0.113.7") != before


def test_a_different_pepper_gives_a_different_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(b"\x03" * 32)
    before = hash_ip("203.0.113.7")
    monkeypatch.setenv("IP_HASH_SALT", "another-pepper")
    get_settings.cache_clear()
    _install(b"\x03" * 32)
    assert hash_ip("203.0.113.7") != before


def test_no_key_means_none_rather_than_an_unkeyed_hash() -> None:
    """Fails closed for privacy: a NULL ip_hash, never a guessable digest."""
    clear_ip_hash_key()
    assert hash_ip("203.0.113.7") is None


@pytest.mark.parametrize("ip", ["2001:db8::1", "::ffff:192.0.2.1", "192.0.2.1"])
def test_ipv6_and_ipv4_mapped_inputs_hash_to_distinct_digests(ip: str) -> None:
    digest = hash_ip(ip)
    assert digest is not None and HEX64.match(digest)
    assert len({hash_ip("2001:db8::1"), hash_ip("::ffff:192.0.2.1"), hash_ip("192.0.2.1")}) == 3


@given(st.ip_addresses().map(str))
def test_the_raw_ip_never_survives_into_the_digest(ip: str) -> None:
    """Callers guard with `if ip`, so the empty string is never passed (auth.py et al.)."""
    digest = hash_ip(ip)
    assert digest is not None and ip not in digest and HEX64.match(digest)


def test_neither_the_key_nor_the_salt_nor_the_pepper_appears_in_a_repr() -> None:
    salt = bytes(range(32))
    _install(salt)
    key = security._current_ip_hash_key
    assert key is not None
    text = repr(key)
    assert key.material.hex() not in text and repr(key.material) not in text
    assert salt.hex() not in text and repr(salt) not in text
    settings_text = repr(get_settings()) + str(get_settings().model_dump())
    assert PLACEHOLDER_PEPPER not in settings_text
    assert "**********" in repr(get_settings())


def test_each_unit_test_starts_with_the_fixture_key() -> None:
    """Amendment G: the autouse fixture installed UUID(int=1)'s key for this test."""
    assert security._current_ip_hash_key is not None
    assert security._current_ip_hash_key.salt_id == UUID(int=1)
