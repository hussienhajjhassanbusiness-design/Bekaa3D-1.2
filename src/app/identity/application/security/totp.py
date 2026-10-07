"""RFC 6238 TOTP, delegated to pyotp.

Nothing here implements the algorithm itself. HOTP/TOTP is easy to write and
easy to write subtly wrong - constant-time comparison, counter windows, base32
padding - and a mistake in any of those weakens the admin boundary silently."""

import hmac
from datetime import UTC, datetime

import pyotp

from app.core.config import get_settings

# One step either side of now, i.e. roughly +/-30s. Enough for a phone whose
# clock has drifted or an administrator typing the last digit as the code
# rolls; wider would meaningfully enlarge the window a stolen code stays live.
_VALID_WINDOW = 1

# 160 bits, the RFC 4226 recommendation, encoded as 32 base32 characters.
_SECRET_LENGTH = 32

# RFC 6238's default step. Exported because replay protection is expressed in
# time-steps, and the caller must bucket timestamps exactly the way this module
# does or the comparison is meaningless.
TOTP_STEP_SECONDS = 30


def generate_secret() -> str:
    """A fresh base32 TOTP secret. pyotp uses `secrets` underneath."""
    return pyotp.random_base32(length=_SECRET_LENGTH)


def provisioning_uri(*, secret: str, account_name: str) -> str:
    """The `otpauth://` URI an authenticator app consumes, usually via QR.

    Note this embeds the raw secret - it is setup material, returned once and
    never logged or persisted."""
    settings = get_settings()
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=settings.mfa_issuer)


def current_step(now: datetime) -> int:
    """The time-step `now` falls in. One number per 30-second bucket."""
    return int(now.timestamp()) // TOTP_STEP_SECONDS


def verify_code_step(*, secret: str, code: str, now: datetime) -> int | None:
    """The time-step the submitted code matched, or None if it matched none.

    Returns the step rather than a bare bool because RFC 6238 5.2 requires the
    verifier to reject an OTP it has already accepted, and "which one was
    this?" is the only thing that makes that check possible. `pyotp.verify`
    answers yes/no and throws the step away, so the window is walked here
    instead.

    Every candidate in the window is compared with `hmac.compare_digest`, and
    the loop deliberately does not break early: returning as soon as a match is
    found would make the response time depend on which step matched, which
    leaks how far a caller's clock has drifted. Malformed or non-ASCII input
    simply fails rather than raising - the caller's answer is the same either
    way, and distinguishing them would hand an attacker a free oracle for what
    the server considers well-formed."""
    try:
        submitted = code.strip().encode("ascii")
    except UnicodeEncodeError:
        return None

    totp = pyotp.TOTP(secret)
    now_step = current_step(now)
    matched: int | None = None
    for offset in range(-_VALID_WINDOW, _VALID_WINDOW + 1):
        step = now_step + offset
        candidate = totp.at(step * TOTP_STEP_SECONDS).encode("ascii")
        if hmac.compare_digest(candidate, submitted):
            matched = step
    return matched


def verify_code(*, secret: str, code: str, now: datetime | None = None) -> bool:
    """Whether the code is valid at all, ignoring replay.

    Only for enrollment confirmation, where no credential has authenticated yet
    so there is no earlier step to compare against. Anything completing a login
    must use `verify_code_step` and enforce the replay rule.

    `now` is optional here, and deliberately not optional on
    `verify_code_step`: that caller has to bucket its replay marker with the
    very same instant it verified against, and a defaulted clock would let the
    two silently drift apart across a step boundary."""
    return verify_code_step(secret=secret, code=code, now=now or datetime.now(UTC)) is not None
