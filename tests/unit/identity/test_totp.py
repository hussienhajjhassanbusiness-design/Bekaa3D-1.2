import base64
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

import pyotp
import pytest

from app.core.config import get_settings
from app.identity.application.security.totp import generate_secret, provisioning_uri, verify_code


@pytest.fixture(autouse=True)
def _mfa_settings() -> None:
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()


def test_generated_secrets_are_valid_base32_of_the_expected_length() -> None:
    secret = generate_secret()

    assert len(secret) == 32
    # Must decode, or an authenticator app cannot consume it at all.
    base64.b32decode(secret)


def test_generated_secrets_are_never_repeated() -> None:
    assert len({generate_secret() for _ in range(50)}) == 50


def test_a_code_from_the_matching_secret_verifies() -> None:
    secret = generate_secret()

    assert verify_code(secret=secret, code=pyotp.TOTP(secret).now())


def test_a_code_from_a_different_secret_is_rejected() -> None:
    assert not verify_code(secret=generate_secret(), code=pyotp.TOTP(generate_secret()).now())


@pytest.mark.parametrize("code", ["", "000000", "abcdef", "12345", "not-a-code", "         "])
def test_wrong_or_malformed_codes_are_rejected_without_raising(code: str) -> None:
    """A malformed code must answer the same way a wrong one does. Raising here
    would let a caller distinguish "badly formed" from "incorrect"."""
    assert not verify_code(secret=generate_secret(), code=code)


def test_surrounding_whitespace_is_tolerated() -> None:
    """Codes get pasted out of an authenticator app, often with a space."""
    secret = generate_secret()

    assert verify_code(secret=secret, code=f"  {pyotp.TOTP(secret).now()}  ")


def test_a_code_from_one_step_ago_still_verifies() -> None:
    """The +/-1 step window: an administrator typing the last digit as the code
    rolls must not be rejected."""
    secret = generate_secret()
    totp = pyotp.TOTP(secret)
    previous = totp.at(datetime.now(UTC) - timedelta(seconds=30))

    assert verify_code(secret=secret, code=previous)


def test_a_code_far_outside_the_window_is_rejected() -> None:
    secret = generate_secret()
    totp = pyotp.TOTP(secret)
    stale = totp.at(datetime.now(UTC) - timedelta(seconds=600))

    assert not verify_code(secret=secret, code=stale)


def test_the_provisioning_uri_carries_the_issuer_and_account() -> None:
    secret = generate_secret()

    uri = provisioning_uri(secret=secret, account_name="admin@example.com")
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert params["secret"] == [secret]
    assert params["issuer"] == [get_settings().mfa_issuer]
    assert "admin@example.com" in unquote(parsed.path)
