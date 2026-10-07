"""Minting and reading the two signed cookies that carry a login session.

Neither token is a source of truth on its own. The access token is trusted for
its short lifetime; the refresh token only says *which* session and version is
being claimed - the `sessions` row decides whether that claim is still valid."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.core.config import get_settings
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import InvalidSessionError

# Pinned explicitly and passed to decode() as a single-element allowlist. Never
# read the algorithm from the token itself - that is the classic "alg: none"
# forgery, where an attacker strips the signature and the library obliges.
_ALGORITHM = "HS256"

_ACCESS_TYPE = "access"
_REFRESH_TYPE = "refresh"


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    role: UserRole
    email_verified: bool
    # Whether this session has cleared the admin second factor (SEC-04). Defaults
    # to False so anything that predates MFA - an older token still inside its
    # 15-minute life, or a caller that does not set it - fails closed at the
    # admin boundary rather than being waved through.
    mfa_completed: bool = False
    # The account's authentication epoch at the moment this token was minted.
    # `current_claims` refuses the token if the account has moved past it, which
    # is what makes a password reset take effect immediately rather than at the
    # next refresh (ADR-018). Defaults to 0 so a token minted before the claim
    # existed still decodes - and still works, right up until that account's
    # first reset.
    auth_epoch: int = 0


@dataclass(frozen=True)
class RefreshTokenClaims:
    session_id: UUID
    token_version: int


def issue_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    role: UserRole,
    email_verified: bool,
    now: datetime,
    mfa_completed: bool = False,
    auth_epoch: int = 0,
) -> str:
    settings = get_settings()
    payload = {
        "typ": _ACCESS_TYPE,
        "sub": str(user_id),
        "sid": str(session_id),
        "role": role.value,
        "ver": email_verified,
        "mfa": mfa_completed,
        # Spelled out rather than abbreviated like its neighbours: the short
        # names above predate it, and a security claim nobody can read at a
        # glance is one nobody checks.
        "auth_epoch": auth_epoch,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=_ALGORITHM)


def issue_refresh_token(
    *, session_id: UUID, token_version: int, expires_at: datetime, now: datetime
) -> str:
    """`exp` matches the session row's deadline exactly, so a rotated token
    never outlives the session it belongs to."""
    settings = get_settings()
    payload = {
        "typ": _REFRESH_TYPE,
        "sid": str(session_id),
        "tv": token_version,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=_ALGORITHM)


def _decode(token: str, *, expected_type: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=[_ALGORITHM],
            # Required, not merely checked when present: a correctly signed
            # token with no `exp` used to be accepted and never expire (BUG-28).
            options={"require": ["exp", "iat", "typ"]},
        )
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, expiry, malformed input - all of which mean the
        # same thing to the caller: this credential cannot be trusted.
        raise InvalidSessionError() from exc

    # Without this check an access token could be replayed as a refresh token
    # (or vice versa), since both are signed with the same key.
    if payload.get("typ") != expected_type:
        raise InvalidSessionError()
    return payload


def decode_access_token(token: str) -> AccessTokenClaims:
    payload = _decode(token, expected_type=_ACCESS_TYPE)
    raw_epoch = payload.get("auth_epoch", 0)
    # Strict, and checked before anything else is read. `bool` is a subclass of
    # `int` in Python, so `isinstance(True, int)` is True and a `"auth_epoch":
    # true` claim would otherwise be silently read as epoch 1. A float, a
    # numeric string or a negative value are all equally malformed. None of them
    # may fall back to the default of 0, because 0 is the one value that matches
    # a never-reset account - a malformed claim failing open would be a bypass,
    # not a compatibility shim.
    if isinstance(raw_epoch, bool) or not isinstance(raw_epoch, int) or raw_epoch < 0:
        raise InvalidSessionError()
    try:
        return AccessTokenClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            role=UserRole(payload["role"]),
            email_verified=bool(payload["ver"]),
            # .get, not [...]: a token minted before this claim existed is still
            # validly signed and must decode, simply without MFA.
            mfa_completed=bool(payload.get("mfa", False)),
            auth_epoch=raw_epoch,
        )
    # AttributeError/TypeError too: `UUID(1)` raises AttributeError, so a claim
    # of the wrong JSON type used to escape as a 500 (BUG-43).
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise InvalidSessionError() from exc


def decode_refresh_token(token: str) -> RefreshTokenClaims:
    payload = _decode(token, expected_type=_REFRESH_TYPE)
    try:
        return RefreshTokenClaims(session_id=UUID(payload["sid"]), token_version=int(payload["tv"]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidSessionError() from exc
