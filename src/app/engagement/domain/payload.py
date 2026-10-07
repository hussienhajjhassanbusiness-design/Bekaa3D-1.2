"""What a notification payload is allowed to be.

Pure domain: no framework, no database. The rules are deliberately thin,
because VS-008 builds the channel and later slices define what travels on it.
"""

import json
from typing import Any

from app.core.text import json_contains_nul
from app.engagement.domain.exceptions import InvalidNotificationPayloadError

# A V1 *technical safety* ceiling, not an SRS-defined business value. Nothing in
# the specification names a payload size; this exists so a defect in a future
# producing slice cannot write a multi-megabyte JSONB row that then has to be
# read back on every page of the notification list. 16 KiB is far more than a
# display payload needs and far less than a runaway one.
MAX_PAYLOAD_BYTES = 16 * 1024

# The discriminator database-design.md refers to when it says "the specific
# event is carried in the JSON payload". VS-008 requires the key to exist and to
# be a non-empty string, and deliberately does **not** constrain its values:
# the concrete events (order placed, payment captured, offer countered) belong
# to the slices that emit them. Requiring the key now rather than later is what
# stops the first two producing slices inventing two different conventions -
# and adding a required field to a populated table later means a backfill.
EVENT_KEY = "event"


def compact_json(payload: dict[str, Any]) -> str:
    """Deterministic, compact, **strict** serialisation, used for measuring size.

    Sorted keys and no whitespace, so the measured size depends only on the
    content - two payloads that differ just in key order must not sit on
    opposite sides of the limit.

    Raises `ValueError` on a payload that is not valid JSON, and `TypeError` on
    a value Python cannot serialise at all. `validate_payload` turns both into
    an `InvalidNotificationPayloadError`.
    """
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
        # Strict JSON, and this is the part that is easy to leave off. By
        # default json.dumps emits the bare tokens NaN, Infinity and -Infinity
        # for those float values - a Python convention that is not JSON, and
        # that PostgreSQL rejects outright in a jsonb column. Without this flag
        # such a payload passes validation here and then fails inside asyncpg
        # at flush time, which means it fails *in the middle of whatever
        # business transaction called create_notification* rather than at the
        # boundary where the caller can do something about it.
        allow_nan=False,
    )


def validate_payload(payload: object) -> dict[str, Any]:
    """Return the payload if it satisfies the contract, or raise with every reason.

    Checks run in dependency order and stop early where a later check could not
    run: there is no point asking whether a string has an `event` key.
    """
    if not isinstance(payload, dict):
        raise InvalidNotificationPayloadError(
            [f"payload must be a JSON object, got {type(payload).__name__}"]
        )

    # JSON objects have string keys. A dict built in Python can have any
    # hashable key, and one with an int key would serialise to a *different*
    # object than the one the caller wrote (json.dumps coerces 1 to "1").
    non_string_keys = [key for key in payload if not isinstance(key, str)]
    if non_string_keys:
        raise InvalidNotificationPayloadError(
            [f"payload keys must be strings, got {type(non_string_keys[0]).__name__}"]
        )

    reasons: list[str] = []

    event = payload.get(EVENT_KEY)
    if event is None:
        reasons.append(f"payload must contain {EVENT_KEY!r}")
    elif not isinstance(event, str):
        reasons.append(f"payload {EVENT_KEY!r} must be a string, got {type(event).__name__}")
    elif not event.strip():
        reasons.append(f"payload {EVENT_KEY!r} must not be empty")

    # JSONB cannot store NUL, even escaped: such a payload used to fail inside
    # the caller's transaction as a database error (BUG-37).
    if json_contains_nul(payload):
        reasons.append("payload strings must not contain NUL characters")

    try:
        size = len(compact_json(payload).encode("utf-8"))
    except RecursionError:
        # Nesting deeper than json.dumps can walk. No display payload is
        # anywhere near this deep; it is a producer bug, reported as one (BUG-37).
        reasons.append("payload is nested too deeply to serialise")
    except (TypeError, ValueError) as exc:
        # Only reachable from internal callers - anything arriving over HTTP has
        # already been through a JSON parser. Caught rather than allowed to
        # propagate so a non-serialisable payload fails as a payload problem
        # instead of as a TypeError from inside the driver at flush time.
        reasons.append(f"payload must be JSON-serialisable: {exc}")
    else:
        if size > MAX_PAYLOAD_BYTES:
            reasons.append(f"payload is {size} bytes, above the {MAX_PAYLOAD_BYTES}-byte limit")

    if reasons:
        raise InvalidNotificationPayloadError(reasons)
    return payload
