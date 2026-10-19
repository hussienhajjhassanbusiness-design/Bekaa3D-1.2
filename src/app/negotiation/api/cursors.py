"""Opaque keyset cursors for the offer lists. Strict: a half-valid cursor would page from
the wrong place, and an instant with no UTC equivalent was a 500 elsewhere (BUG-36)."""

import base64
import binascii
from datetime import UTC, datetime
from uuid import UUID

from fastapi.exceptions import RequestValidationError

from app.negotiation.application.ports import QueueKey

_SEPARATOR = "|"
_BAD = "cursor is not a valid pagination cursor"


def _encode(*parts: str) -> str:
    raw = _SEPARATOR.join(parts).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(raw: str, count: int) -> list[str]:
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise _invalid("cursor", _BAD) from exc
    parts = text.split(_SEPARATOR)
    if len(parts) != count:
        raise _invalid("cursor", _BAD)
    return parts


def _invalid(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


def utc(moment: datetime | None, field: str) -> datetime | None:
    """A query timestamp as UTC; naive or unrepresentable -> 422."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        raise _invalid(field, "must carry a UTC offset, e.g. 2026-10-01T00:00Z")
    try:
        return moment.astimezone(UTC)
    except OverflowError as exc:
        raise _invalid(field, f"{field} is out of range") from exc


def _instant(raw: str) -> datetime:
    try:
        moment = utc(datetime.fromisoformat(raw), "cursor")
    except ValueError as exc:
        raise _invalid("cursor", _BAD) from exc
    if moment is None:
        raise _invalid("cursor", _BAD)
    return moment


def _uuid(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise _invalid("cursor", _BAD) from exc


def encode_customer(created_at: datetime, offer_id: UUID) -> str:
    return _encode(created_at.isoformat(), str(offer_id))


def decode_customer(raw: str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    created, offer_id = _decode(raw, 2)
    return _instant(created), _uuid(offer_id)


def encode_queue(key: QueueKey) -> str:
    rank, at, offer_id = key
    return _encode(str(rank), at.isoformat(), str(offer_id))


def decode_queue(raw: str | None) -> QueueKey | None:
    if raw is None:
        return None
    rank, at, offer_id = _decode(raw, 3)
    if rank not in {"0", "1", "2", "3"}:
        raise _invalid("cursor", _BAD)
    return int(rank), _instant(at), _uuid(offer_id)
