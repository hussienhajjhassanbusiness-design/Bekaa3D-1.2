import hashlib
import hmac
import secrets
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


def hash_ip(ip_address: str) -> str:
    """Salted, one-way hash so audit/download logs can detect repeat activity
    without storing a raw IP address. Rotate IP_HASH_SALT periodically (the
    rotate_ip_salt job, SRS §23) to make historical hashes unlinkable."""
    settings = get_settings()
    salted = f"{settings.ip_hash_salt}:{ip_address}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()
