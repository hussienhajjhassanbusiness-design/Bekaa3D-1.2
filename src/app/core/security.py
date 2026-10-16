import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from uuid import UUID

from app.core.config import get_settings


def csrf_token_for_session(session_id: UUID) -> str:
    """Derive this session's CSRF token as HMAC(CSRF_SECRET, session_id).

    Deriving rather than storing a random value has two benefits: nothing extra
    to persist, and the token is *bound to the session*. Plain double-submit
    only checks that cookie and header agree, so an attacker who can write a
    cookie (e.g. from a compromised subdomain) can set both halves to a value
    they chose. A bound token defeats that - they cannot forge the HMAC for
    someone else's session without the server secret."""
    settings = get_settings()
    return hmac.new(
        settings.csrf_secret.encode("utf-8"),
        str(session_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(*, session_id: UUID, presented: str | None) -> bool:
    if not presented:
        return False
    # Compared as bytes: compare_digest raises TypeError for a str holding any
    # non-ASCII character, and Starlette decodes headers as latin-1, so one
    # such header byte turned every CSRF-protected route into a 500 (BUG-44).
    return secrets.compare_digest(
        presented.encode("utf-8"), csrf_token_for_session(session_id).encode("utf-8")
    )


_IP_HASH_KEY_LABEL = b"bekaa3d/ip-hash/v2:"


@dataclass(frozen=True)
class _IpHashKey:
    salt_id: UUID
    loaded_at: float  # time.monotonic() at install
    material: bytes = field(repr=False)  # the derived key; never printed


_current_ip_hash_key: _IpHashKey | None = None


def install_ip_hash_key(*, salt_id: UUID, salt: bytes, now: float) -> None:
    """Derive K = HMAC(pepper, label || salt) and make it current (ADR-028).
    Neither the env pepper nor the database salt alone reveals anything."""
    global _current_ip_hash_key
    pepper = get_settings().ip_hash_salt.get_secret_value().encode("utf-8")
    material = hmac.new(pepper, _IP_HASH_KEY_LABEL + salt, hashlib.sha256).digest()
    _current_ip_hash_key = _IpHashKey(salt_id=salt_id, loaded_at=now, material=material)


def clear_ip_hash_key() -> None:
    global _current_ip_hash_key
    _current_ip_hash_key = None


def ip_hash_key_loaded_at() -> float | None:
    key = _current_ip_hash_key
    return key.loaded_at if key is not None else None


def hash_ip(ip_address: str) -> str | None:
    """Keyed one-way hash of an IP for session and audit rows (SEC-25, ADR-028).
    None until the keyring has loaded a key; the monthly rotation unlinks old hashes."""
    key = _current_ip_hash_key
    if key is None:
        return None
    return hmac.new(key.material, ip_address.encode("utf-8"), hashlib.sha256).hexdigest()
