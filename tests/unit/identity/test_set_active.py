"""`User.set_active` and the VS-009 admin cursor - the two pieces of the slice
that are decidable without a database.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.exceptions import RequestValidationError

from app.identity.api.admin_users import _decode_cursor, _encode_cursor, _parse_cursor
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole

CREATED = datetime(2026, 1, 1, tzinfo=UTC)
LATER = CREATED + timedelta(days=1)


def make_user(*, is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email="someone@example.com",
        password_hash="argon2-hash",
        role=UserRole.CUSTOMER,
        email_verified_at=CREATED,
        is_active=is_active,
        anonymized_at=None,
        deleted_at=None,
        created_at=CREATED,
        updated_at=CREATED,
    )


# --------------------------------------------------------------------------
# set_active
# --------------------------------------------------------------------------


def test_deactivating_an_active_account_reports_the_change() -> None:
    user = make_user(is_active=True)

    assert user.set_active(is_active=False, at=LATER) is True
    assert user.is_active is False
    assert user.updated_at == LATER


def test_activating_an_inactive_account_reports_the_change() -> None:
    user = make_user(is_active=False)

    assert user.set_active(is_active=True, at=LATER) is True
    assert user.is_active is True
    assert user.updated_at == LATER


@pytest.mark.parametrize("state", [True, False])
def test_restating_the_current_value_changes_nothing(state: bool) -> None:
    """The false return is what stops a no-op PATCH revoking sessions or writing
    an audit row describing an event that did not happen."""
    user = make_user(is_active=state)

    assert user.set_active(is_active=state, at=LATER) is False
    assert user.is_active is state
    assert user.updated_at == CREATED


def test_set_active_never_touches_the_authentication_epoch() -> None:
    """Deactivation must also void live credentials, but that is
    `invalidate_credentials`, called by the use case. Folding it in here would
    bump the epoch on reactivation too, where there is nothing to void."""
    user = make_user(is_active=True)
    before = user.auth_epoch

    user.set_active(is_active=False, at=LATER)

    assert user.auth_epoch == before


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------


def test_a_cursor_round_trips() -> None:
    user_id = uuid.uuid4()
    moment = datetime(2026, 9, 15, 10, 39, 27, 123456, tzinfo=UTC)

    assert _parse_cursor(_encode_cursor(moment, user_id)) == (moment, user_id)


def test_the_cursor_is_urlsafe_and_unpadded() -> None:
    """It travels in a query string, so it must survive one without escaping."""
    cursor = _encode_cursor(datetime.now(UTC), uuid.uuid4())

    assert "=" not in cursor
    assert "+" not in cursor
    assert "/" not in cursor


def test_an_absent_cursor_is_not_an_error() -> None:
    assert _parse_cursor(None) is None
    assert _decode_cursor(None) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not-base64-at-all!!",
        "Zm9vYmFy",  # valid base64, no separator
        "bm9wZXxub3Bl",  # "nope|nope" - separator present, both halves junk
        # A valid UUID with an unparseable timestamp.
        "bm90LWEtdGltZXwwMTliMzY4Ni0wMDAwLTcwMDAtODAwMC0wMDAwMDAwMDAwMDA",
    ],
)
def test_a_malformed_cursor_is_rejected_rather_than_guessed_at(raw: str) -> None:
    with pytest.raises(ValueError):
        _parse_cursor(raw)


def test_a_naive_timestamp_is_rejected() -> None:
    """The column is timestamptz. A naive datetime would be compared under the
    server's timezone assumption rather than the one the cursor was minted with,
    which silently shifts the page boundary."""
    raw = f"2026-09-15T10:39:27|{uuid.uuid4()}"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    with pytest.raises(ValueError):
        _parse_cursor(encoded)


def test_decode_reports_a_bad_cursor_as_a_query_parameter_error() -> None:
    """422 VALIDATION_ERROR naming `cursor`, not a 500 and not a silently
    ignored value - the VS-007 regression."""
    with pytest.raises(RequestValidationError) as caught:
        _decode_cursor("not-a-cursor")

    assert any("cursor" in error["loc"] for error in caught.value.errors())
