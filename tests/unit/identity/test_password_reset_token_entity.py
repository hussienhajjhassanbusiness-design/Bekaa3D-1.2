import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.identity.domain.entities import PasswordResetToken
from app.identity.domain.exceptions import (
    InvalidPasswordResetTokenError,
    PasswordResetTokenExpiredError,
)


def _token(
    *, used_at: datetime | None = None, ttl: timedelta = timedelta(hours=1)
) -> PasswordResetToken:
    now = datetime.now(UTC)
    return PasswordResetToken(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        token_hash="a" * 64,
        expires_at=now + ttl,
        used_at=used_at,
        created_at=now,
    )


def test_an_unused_live_token_can_be_marked_used() -> None:
    token = _token()
    at = datetime.now(UTC)

    token.mark_used(at)

    assert token.used_at == at
    assert token.is_used


def test_a_used_token_cannot_be_redeemed_twice() -> None:
    token = _token(used_at=datetime.now(UTC) - timedelta(minutes=1))

    with pytest.raises(InvalidPasswordResetTokenError):
        token.mark_used(datetime.now(UTC))


def test_an_expired_token_is_rejected_as_expired() -> None:
    token = _token(ttl=timedelta(seconds=-1))

    with pytest.raises(PasswordResetTokenExpiredError):
        token.mark_used(datetime.now(UTC))


def test_expiry_is_inclusive_at_the_deadline() -> None:
    """`at >= expires_at`, not `>`. A token whose window closed at exactly this
    instant is spent - the boundary must not be redeemable."""
    token = _token()

    with pytest.raises(PasswordResetTokenExpiredError):
        token.mark_used(token.expires_at)


def test_a_used_token_reads_as_invalid_even_after_it_also_expires() -> None:
    """The used check runs before the expiry check on purpose. If the order were
    reversed, replaying one token would answer 400 while its window was open and
    410 afterwards - a status code that changes with the clock tells an attacker
    when the token was issued."""
    token = _token(used_at=datetime.now(UTC), ttl=timedelta(seconds=-1))

    with pytest.raises(InvalidPasswordResetTokenError):
        token.mark_used(datetime.now(UTC))
