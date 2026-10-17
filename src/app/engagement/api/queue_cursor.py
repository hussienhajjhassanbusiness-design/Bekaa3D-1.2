"""Cursor and date-range helpers for the admin queues ordered by (status, created_at, id)."""

import base64
import binascii
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from fastapi.exceptions import RequestValidationError

_SEPARATOR = "|"


def encode_cursor(state: StrEnum, created_at: datetime, row_id: UUID) -> str:
    raw = _SEPARATOR.join((state.value, created_at.isoformat(), str(row_id)))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _parse[S: StrEnum](raw: str, states: type[S]) -> tuple[S, datetime, UUID]:
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
        state_raw, created_raw, id_raw = decoded.split(_SEPARATOR)
        parsed = states(state_raw), datetime.fromisoformat(created_raw), UUID(id_raw)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("cursor is not a valid pagination cursor") from exc
    if not is_utc_representable(parsed[1]):
        raise ValueError("cursor is not a valid pagination cursor")
    return parsed


def is_utc_representable(moment: datetime) -> bool:
    """Aware and convertible to UTC; asyncpg overflowed on the rest (BUG-36)."""
    if moment.tzinfo is None:
        return False
    try:
        moment.astimezone(UTC)
    except OverflowError:
        return False
    return True


def invalid_query(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


def decode_cursor[S: StrEnum](raw: str | None, states: type[S]) -> tuple[S, datetime, UUID] | None:
    if raw is None:
        return None
    try:
        return _parse(raw, states)
    except ValueError as exc:
        raise invalid_query("cursor", str(exc)) from exc


def check_range(
    lower: datetime | None,
    upper: datetime | None,
    *,
    names: tuple[str, str] = ("created_after", "created_before"),
) -> None:
    for field, moment in zip(names, (lower, upper), strict=True):
        if moment is not None and not is_utc_representable(moment):
            raise invalid_query(
                field, "must be a timestamp with a UTC offset, e.g. 2026-10-01T00:00Z"
            )
    if lower is not None and upper is not None and upper <= lower:
        raise invalid_query(names[1], f"must be later than {names[0]}")
