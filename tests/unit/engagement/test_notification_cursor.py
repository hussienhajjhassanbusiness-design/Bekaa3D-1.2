"""The pagination cursor, in isolation.

The endpoint tests walk real pages; these check the encoding itself, where the
interesting cases (a tampered value, a naive timestamp) are awkward to produce
through HTTP but trivial here.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.engagement.api.notifications import _encode_cursor, _parse_cursor


def test_a_cursor_round_trips_both_halves() -> None:
    """Both, not just the timestamp: the `id` is what makes the cursor address a
    single row when several share a `created_at`."""
    created_at = datetime.now(UTC)
    notification_id = uuid.uuid4()

    decoded = _parse_cursor(_encode_cursor(created_at, notification_id))

    assert decoded == (created_at, notification_id)


def test_no_cursor_means_the_first_page() -> None:
    assert _parse_cursor(None) is None


def test_the_cursor_is_url_safe_and_unpadded() -> None:
    """It travels in a query string, so `+`, `/` and `=` would need escaping."""
    cursor = _encode_cursor(datetime.now(UTC), uuid.uuid4())
    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_microsecond_precision_survives_the_round_trip() -> None:
    """A cursor that lost sub-second precision would re-serve or skip every row
    written inside the same second as the page boundary."""
    created_at = datetime.now(UTC).replace(microsecond=123_456)
    decoded = _parse_cursor(_encode_cursor(created_at, uuid.uuid4()))
    assert decoded is not None
    assert decoded[0].microsecond == 123_456


def test_a_timezone_offset_is_preserved_as_the_same_instant() -> None:
    """A fixed offset rather than a named zone, so the test does not depend on
    the machine's timezone database."""
    created_at = datetime.now(UTC).astimezone(timezone(timedelta(hours=3)))
    decoded = _parse_cursor(_encode_cursor(created_at, uuid.uuid4()))
    assert decoded is not None
    assert decoded[0] == created_at


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param("!!!not-base64!!!", id="not-base64"),
        pytest.param(base64.urlsafe_b64encode(b"no-separator").decode().rstrip("="), id="no-sep"),
        pytest.param(
            base64.urlsafe_b64encode(b"not-a-date|" + str(uuid.uuid4()).encode())
            .decode()
            .rstrip("="),
            id="bad-timestamp",
        ),
        pytest.param(
            base64.urlsafe_b64encode(datetime.now(UTC).isoformat().encode() + b"|not-a-uuid")
            .decode()
            .rstrip("="),
            id="bad-uuid",
        ),
        pytest.param(
            base64.urlsafe_b64encode(
                datetime.now().isoformat().encode() + b"|" + str(uuid.uuid4()).encode()
            )
            .decode()
            .rstrip("="),
            id="naive-timestamp",
        ),
    ],
)
def test_a_tampered_cursor_is_refused(cursor: str) -> None:
    """Every half is parsed strictly. A cursor that decoded into a half-valid
    pair would not fail loudly - it would silently page from the wrong place,
    which is exactly the VS-007 failure this design is avoiding."""
    with pytest.raises(ValueError):
        _parse_cursor(cursor)
