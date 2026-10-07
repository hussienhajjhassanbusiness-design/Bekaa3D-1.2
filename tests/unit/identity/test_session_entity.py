from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.identity.domain.entities import Session
from app.identity.domain.exceptions import (
    InvalidSessionError,
    RefreshTokenReuseError,
    SessionExpiredError,
    SessionRevokedError,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
CURRENT_HASH = "a" * 64


def make_session(**overrides: object) -> Session:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "refresh_token_hash": CURRENT_HASH,
        "token_version": 3,
        "expires_at": NOW + timedelta(days=30),
        "last_used_at": None,
        "rotated_at": None,
        "revoked_at": None,
        "reuse_detected_at": None,
        "ip_hash": None,
        "user_agent": None,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Session(**defaults)  # type: ignore[arg-type]


def test_authorize_rotation_accepts_the_current_token() -> None:
    session = make_session()

    session.authorize_rotation(presented_token_hash=CURRENT_HASH, presented_version=3, at=NOW)


def test_rotate_advances_version_and_replaces_the_hash() -> None:
    session = make_session()

    session.rotate(new_token_hash="b" * 64, at=NOW)

    assert session.refresh_token_hash == "b" * 64
    assert session.token_version == 4
    assert session.rotated_at == NOW
    assert session.last_used_at == NOW


def test_an_older_token_version_is_reuse_not_merely_invalid() -> None:
    """The whole point of token_version: a validly signed token carrying an
    older version can only be a replay of a token that was already rotated."""
    session = make_session(token_version=3)

    with pytest.raises(RefreshTokenReuseError):
        session.authorize_rotation(presented_token_hash=CURRENT_HASH, presented_version=2, at=NOW)


def test_right_version_but_wrong_hash_is_invalid() -> None:
    session = make_session()

    with pytest.raises(InvalidSessionError):
        session.authorize_rotation(presented_token_hash="c" * 64, presented_version=3, at=NOW)


def test_revoked_session_cannot_rotate() -> None:
    session = make_session(revoked_at=NOW - timedelta(minutes=1))

    with pytest.raises(SessionRevokedError):
        session.authorize_rotation(presented_token_hash=CURRENT_HASH, presented_version=3, at=NOW)


def test_expired_session_cannot_rotate() -> None:
    session = make_session(expires_at=NOW - timedelta(seconds=1))

    with pytest.raises(SessionExpiredError):
        session.authorize_rotation(presented_token_hash=CURRENT_HASH, presented_version=3, at=NOW)


def test_revocation_is_checked_before_reuse() -> None:
    """An already-revoked session reports revoked, not reuse - it is already
    dead, so there is no live session left to kill."""
    session = make_session(revoked_at=NOW - timedelta(minutes=1))

    with pytest.raises(SessionRevokedError):
        session.authorize_rotation(presented_token_hash=CURRENT_HASH, presented_version=1, at=NOW)


def test_mark_reuse_detected_kills_the_session() -> None:
    session = make_session()

    session.mark_reuse_detected(NOW)

    assert session.reuse_detected_at == NOW
    assert session.revoked_at == NOW
    assert not session.is_live(NOW)


def test_revoke_is_idempotent_and_keeps_the_first_timestamp() -> None:
    first = NOW - timedelta(hours=1)
    session = make_session(revoked_at=first)

    session.revoke(NOW)

    assert session.revoked_at == first


def test_is_live_requires_neither_revoked_nor_expired() -> None:
    assert make_session().is_live(NOW)
    assert not make_session(revoked_at=NOW).is_live(NOW)
    assert not make_session(expires_at=NOW).is_live(NOW)
