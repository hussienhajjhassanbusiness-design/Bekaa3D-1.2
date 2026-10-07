"""Encrypting the TOTP secret that `mfa_credentials.secret_ciphertext` stores.

Hashing is not an option here, unlike passwords and recovery codes: verifying a
TOTP means *recomputing* it, which needs the original secret back. So this is
reversible encryption, and the only real question is what protects the key.

Fernet is used rather than raw AES because it is authenticated (AES-128-CBC
plus HMAC-SHA256). Unauthenticated ciphertext would let anyone with database
write access flip bits in a stored secret and steer it toward a value they
know; the HMAC makes that tampering fail loudly instead."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretDecryptionError(Exception):
    """Stored ciphertext could not be decrypted or failed its authentication tag.

    Means the key changed (rotation, wrong environment) or the row was
    tampered with. Deliberately not an identity domain error - it is an
    operational fault, not a user-facing authentication outcome."""


def _fernet() -> Fernet:
    """Derive the Fernet key from MFA_SECRET_KEY.

    Fernet wants 32 bytes of urlsafe-base64; the setting is a hex string chosen
    by an operator. SHA-256 maps any such value onto exactly 32 bytes. That is
    sufficient *because the input is already high-entropy* - this is a key
    derivation from a secret, not password stretching, so no salt or KDF cost
    is required. Never point this at something guessable."""
    settings = get_settings()
    digest = hashlib.sha256(settings.mfa_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> bytes:
    return _fernet().encrypt(secret.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError() from exc
