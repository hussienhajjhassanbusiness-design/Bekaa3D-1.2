"""The notification type and payload contract.

Pure domain tests, no database. VS-008 builds the channel rather than the
events that travel on it, so the rules here are deliberately few - but each one
is the only thing standing between a future producing slice and a malformed row
that the list endpoint then has to render.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.engagement.api.schemas import NotificationRead
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.domain.exceptions import InvalidNotificationPayloadError
from app.engagement.domain.payload import MAX_PAYLOAD_BYTES, compact_json, validate_payload

# The six from database-design.md 12.3, written out rather than derived from the
# enum: a test that builds its expectation from the thing under test would pass
# just as happily if a value were deleted.
DOCUMENTED_TYPES = ("account", "order", "payment", "refund", "offer", "download")


# --------------------------------------------------------------------------
# Type
# --------------------------------------------------------------------------


def test_the_enum_holds_exactly_the_six_documented_categories() -> None:
    assert tuple(member.value for member in NotificationType) == DOCUMENTED_TYPES


def test_no_concrete_event_has_leaked_into_the_category_enum() -> None:
    """The enum is a *high-level category*; the specific event rides in the
    payload. Stated from the other direction so the assertion still bites if
    someone adds `order_shipped` alongside a matching entry above."""
    for member in NotificationType:
        assert "." not in member.value
        assert "_" not in member.value


# --------------------------------------------------------------------------
# Payload shape
# --------------------------------------------------------------------------


def test_a_well_formed_payload_is_returned_unchanged() -> None:
    payload = {"event": "account.test", "detail": "anything"}
    assert validate_payload(payload) == payload


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(["event"], id="array"),
        pytest.param("event", id="string"),
        pytest.param(7, id="number"),
        pytest.param(None, id="null"),
        pytest.param(True, id="boolean"),
    ],
)
def test_a_payload_that_is_not_an_object_is_rejected(payload: object) -> None:
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload(payload)


def test_non_string_keys_are_rejected() -> None:
    """JSON objects have string keys. A dict with an int key would serialise to
    a *different* object than the caller wrote - json.dumps turns 1 into "1"."""
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": "account.test", 1: "one"})


# --------------------------------------------------------------------------
# The event discriminator
# --------------------------------------------------------------------------


def test_the_event_key_is_required() -> None:
    with pytest.raises(InvalidNotificationPayloadError) as raised:
        validate_payload({"detail": "no event here"})
    assert any("event" in reason for reason in raised.value.reasons)


@pytest.mark.parametrize(
    "event",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace-only"),
        pytest.param(7, id="number"),
        pytest.param(None, id="null"),
        pytest.param(["account.test"], id="array"),
    ],
)
def test_an_event_that_is_not_a_non_empty_string_is_rejected(event: object) -> None:
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": event})


def test_event_values_are_not_constrained_in_v1() -> None:
    """Deliberate: the concrete events belong to the slices that emit them.
    This test exists to make that a decision rather than an oversight - if a
    registry is added later, it should fail and be updated consciously."""
    for event in ("account.test", "order.test", "anything.at.all", "x"):
        assert validate_payload({"event": event})["event"] == event


# --------------------------------------------------------------------------
# Size
# --------------------------------------------------------------------------


def test_a_payload_at_the_limit_is_accepted() -> None:
    filler = "x" * (MAX_PAYLOAD_BYTES - len(compact_json({"event": "a", "d": ""}).encode()))
    payload = {"event": "a", "d": filler}
    assert len(compact_json(payload).encode("utf-8")) == MAX_PAYLOAD_BYTES
    assert validate_payload(payload) == payload


def test_a_payload_one_byte_over_the_limit_is_rejected() -> None:
    filler = "x" * (MAX_PAYLOAD_BYTES - len(compact_json({"event": "a", "d": ""}).encode()) + 1)
    with pytest.raises(InvalidNotificationPayloadError) as raised:
        validate_payload({"event": "a", "d": filler})
    assert any("limit" in reason for reason in raised.value.reasons)


def test_size_is_measured_in_utf8_bytes_not_characters() -> None:
    """A multi-byte character costs what it actually costs on disk. Measuring
    `len(str)` would let a payload roughly three times the limit through."""
    payload = {"event": "a", "d": "é" * MAX_PAYLOAD_BYTES}
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload(payload)


def test_key_order_cannot_change_whether_a_payload_fits() -> None:
    one = {"event": "a", "b": "x", "c": "y"}
    other = {"c": "y", "b": "x", "event": "a"}
    assert compact_json(one) == compact_json(other)


def test_a_non_serialisable_payload_fails_as_a_payload_problem() -> None:
    """Reachable only from internal callers, and caught so it surfaces here
    rather than as a TypeError from inside the driver at flush time."""
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": "account.test", "d": object()})


# --------------------------------------------------------------------------
# Strict JSON
#
# Python's json module is more permissive than JSON itself. These values are
# the gap between the two, and the payload column is `jsonb` - PostgreSQL
# rejects them, so anything that slips through here fails later, inside the
# business transaction that called create_notification rather than at the
# boundary where the caller could still react.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="inf"),
        pytest.param(float("-inf"), id="-inf"),
    ],
)
def test_python_only_float_values_are_rejected(value: float) -> None:
    """`json.dumps` writes these as the bare tokens NaN / Infinity / -Infinity,
    which no JSON parser is required to accept and `jsonb` refuses."""
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": "account.test", "amount": value})


def test_a_nan_nested_deep_in_the_payload_is_still_rejected() -> None:
    """Serialisation walks the whole structure, so the check is not limited to
    top-level values - which a hand-written type check over `payload.values()`
    would have been."""
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": "account.test", "d": {"totals": [1, 2, float("nan")]}})


def test_a_datetime_is_not_a_json_value() -> None:
    """The likeliest real mistake: a producing slice passing a model attribute
    straight through. It must fail as a payload problem, not as a raw TypeError
    escaping the domain layer."""
    with pytest.raises(InvalidNotificationPayloadError):
        validate_payload({"event": "account.test", "value": datetime.now(UTC)})


def test_the_serialiser_itself_refuses_non_standard_tokens() -> None:
    """Asserted directly on `compact_json`, because it is also what measures the
    size limit - a permissive serialiser there would mean the stored bytes and
    the measured bytes were not the same thing."""
    with pytest.raises(ValueError):
        compact_json({"event": "a", "d": float("nan")})


# --------------------------------------------------------------------------
# read is derived, never stored
# --------------------------------------------------------------------------


def _notification(read_at: datetime | None) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=NotificationType.ACCOUNT,
        payload={"event": "account.test"},
        read_at=read_at,
        created_at=datetime.now(UTC),
    )


def test_read_is_false_exactly_when_read_at_is_null() -> None:
    assert _notification(None).read is False
    assert _notification(datetime.now(UTC)).read is True


def test_the_api_schema_derives_read_and_never_exposes_read_at() -> None:
    """`read_at` is not part of the V1 contract (api-endpoints.md 29.8 defines a
    boolean `read`), but the flag must always agree with it."""
    for read_at in (None, datetime.now(UTC)):
        notification = _notification(read_at)
        body = NotificationRead.from_notification(notification).model_dump()
        assert body["read"] is (read_at is not None)
        assert "read_at" not in body
        assert set(body) == {"id", "type", "payload", "read", "created_at"}
