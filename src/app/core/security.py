import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.phone import E164_PATTERN


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


# The salt's weak values (VS-028 plan Q5); dev and test may run the .env.example placeholder.
PHONE_HASH_SALT_MIN_LENGTH = 32
PHONE_HASH_SALT_PLACEHOLDER_PREFIX = "generate_with__"
_PHONE_HASH_SALT_LAX_ENVIRONMENTS = frozenset({"development", "test"})


class ConfigurationError(RuntimeError):
    """A setting that must stop the process at boot; the message never holds its value."""


def check_phone_hash_salt(settings: Settings) -> None:
    """Refuse a short or placeholder PHONE_HASH_SALT outside development and test, in
    `main.py` and `worker.py` alike: it can never be rotated later (ADR-024 d6)."""
    if settings.environment in _PHONE_HASH_SALT_LAX_ENVIRONMENTS:
        return
    salt = settings.phone_hash_salt.get_secret_value()
    if len(salt) < PHONE_HASH_SALT_MIN_LENGTH or salt.startswith(
        PHONE_HASH_SALT_PLACEHOLDER_PREFIX
    ):
        raise ConfigurationError(
            f"PHONE_HASH_SALT must be a generated secret of at least "
            f"{PHONE_HASH_SALT_MIN_LENGTH} characters in {settings.environment!r}."
        )


def hash_phone(e164: str) -> str:
    """HMAC-SHA256 of a normalised E.164 phone keyed by PHONE_HASH_SALT, lowercase hex
    (ADR-024 d6). A raw spelling raises ValueError, so two spellings never hash apart."""
    if E164_PATTERN.fullmatch(e164) is None:
        raise ValueError("hash_phone takes a normalised E.164 Lebanese number")
    key = get_settings().phone_hash_salt.get_secret_value().encode("utf-8")
    return hmac.new(key, e164.encode("utf-8"), hashlib.sha256).hexdigest()
