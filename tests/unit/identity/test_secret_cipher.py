import os
from collections.abc import Generator

import pytest

from app.core.config import get_settings
from app.identity.application.security.secret_cipher import (
    SecretDecryptionError,
    decrypt_secret,
    encrypt_secret,
)
from app.identity.application.security.totp import generate_secret


@pytest.fixture(autouse=True)
def _mfa_settings() -> Generator[None]:
    os.environ["MFA_SECRET_KEY"] = "a" * 64
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_a_secret_survives_a_round_trip() -> None:
    secret = generate_secret()

    assert decrypt_secret(encrypt_secret(secret)) == secret


def test_the_ciphertext_never_contains_the_plaintext() -> None:
    secret = generate_secret()

    ciphertext = encrypt_secret(secret)

    assert isinstance(ciphertext, bytes)
    assert secret.encode("utf-8") not in ciphertext


def test_encrypting_twice_produces_different_ciphertext() -> None:
    """Fernet includes a random IV, so identical secrets do not produce
    identical rows - otherwise the table would reveal which administrators
    happen to share a secret."""
    secret = generate_secret()

    assert encrypt_secret(secret) != encrypt_secret(secret)


def test_tampered_ciphertext_is_rejected_rather_than_silently_decrypted() -> None:
    """The authentication tag is the point of using Fernet over raw AES:
    someone with database write access must not be able to steer a stored
    secret toward a value they control."""
    ciphertext = bytearray(encrypt_secret(generate_secret()))
    ciphertext[-1] ^= 0x01

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(bytes(ciphertext))


def test_ciphertext_from_a_different_key_is_rejected() -> None:
    ciphertext = encrypt_secret(generate_secret())

    os.environ["MFA_SECRET_KEY"] = "b" * 64
    get_settings.cache_clear()

    with pytest.raises(SecretDecryptionError):
        decrypt_secret(ciphertext)


def test_garbage_is_rejected() -> None:
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(b"not-a-fernet-token")
