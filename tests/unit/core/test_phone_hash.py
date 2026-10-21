"""The contact-phone hash and its salt's boot check (VS-028 PR A; ADR-024 d6, plan Q5)."""

import hashlib
import hmac
import re

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.phone import normalise_lebanese_phone
from app.core.security import ConfigurationError, check_phone_hash_salt, hash_phone

KEY = "known-answer-key-0123456789abcdef"
# Computed outside the code under test: `printf '+9613123456' | openssl dgst -sha256 -hmac KEY`.
KNOWN = "a9acddce0e11c485a087d7a7cb26ac5435f0745f2b2c6e3bef6a54d52ff25a79"
GOOD_SALT = "0123456789abcdef" * 4


@pytest.fixture
def salt(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("PHONE_HASH_SALT", KEY)
    get_settings.cache_clear()
    return KEY


@pytest.mark.usefixtures("salt")
def test_the_hash_is_hmac_sha256_of_the_e164_number() -> None:
    assert hash_phone("+9613123456") == KNOWN


@pytest.mark.usefixtures("salt")
def test_three_spellings_give_one_number_and_one_hash() -> None:
    spellings = ("+961 3 123 456", "03123456", "9613123456")
    numbers = {normalise_lebanese_phone(raw) for raw in spellings}
    assert numbers == {"+9613123456"}
    assert {hash_phone(n) for n in numbers} == {KNOWN}


@pytest.mark.usefixtures("salt")
def test_the_hash_is_64_lowercase_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", hash_phone("+96171123456"))


def test_another_key_gives_another_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHONE_HASH_SALT", KEY + "x")
    get_settings.cache_clear()
    other = hash_phone("+9613123456")
    assert other != KNOWN
    expected = hmac.new((KEY + "x").encode(), b"+9613123456", hashlib.sha256).hexdigest()
    assert other == expected


@pytest.mark.usefixtures("salt")
@pytest.mark.parametrize("raw", ["03123456", "+961 3 123 456", "9613123456", "+33612345678", ""])
def test_a_raw_spelling_is_refused(raw: str) -> None:
    """Only the normalised form is hashed, so two spellings can never hash apart."""
    with pytest.raises(ValueError):
        hash_phone(raw)


def _settings(environment: str, value: str) -> Settings:
    return get_settings().model_copy(
        update={"environment": environment, "phone_hash_salt": SecretStr(value)}
    )


WEAK = [
    pytest.param("a" * 31, id="short"),
    pytest.param("generate_with__openssl_rand_hex_32", id="placeholder"),
    pytest.param("generate_with__" + "a" * 40, id="placeholder-prefix-long"),
]


@pytest.mark.parametrize("environment", ["production", "staging", "prod"])
@pytest.mark.parametrize("value", WEAK)
def test_a_weak_salt_is_refused_outside_development_and_test(environment: str, value: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        check_phone_hash_salt(_settings(environment, value))
    assert value not in str(raised.value)
    assert "PHONE_HASH_SALT" in str(raised.value)


@pytest.mark.parametrize("environment", ["development", "test"])
@pytest.mark.parametrize("value", WEAK)
def test_development_and_test_accept_the_placeholder(environment: str, value: str) -> None:
    check_phone_hash_salt(_settings(environment, value))


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_a_generated_salt_passes_everywhere(environment: str) -> None:
    check_phone_hash_salt(_settings(environment, GOOD_SALT))
    check_phone_hash_salt(_settings(environment, "a" * 32))
