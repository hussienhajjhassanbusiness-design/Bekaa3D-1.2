"""Opaque keyset cursors for the admin and storefront product lists. A cursor is bound
to its sort and, for a search, pins the search mode: misuse or tampering is a 422."""

import base64
import binascii
import json
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi.exceptions import RequestValidationError

from app.catalog.api.product_schemas import PG_BIGINT_MAX
from app.catalog.domain.storefront import MAX_RATING, RATING_STEP, CursorKey, SearchMode


def bad_query(name: str, message: str) -> RequestValidationError:
    return RequestValidationError([{"loc": ("query", name), "msg": message, "type": "value_error"}])


def _key_kind(sort: str) -> str:
    return sort.removeprefix("-")


def encode_cursor(
    sort: str, key: CursorKey, product_id: UUID, mode: SearchMode | None = None
) -> str:
    raw_key: Any = key.isoformat() if isinstance(key, datetime) else key
    if isinstance(key, Decimal):
        raw_key = str(key)
    payload = {"s": sort, "k": raw_key, "i": str(product_id)}
    if mode is not None:
        payload["m"] = mode.value
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode("ascii").rstrip("=")


def _parse_key(kind: str, key: Any) -> CursorKey:
    if kind == "created_at":
        parsed = datetime.fromisoformat(key)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    # Keys are bounded to what their column holds, so a forged one is a 422, not a DB error.
    if kind == "average_rating":
        if type(key) is not str:
            raise ValueError
        rating = Decimal(key)
        if not rating.is_finite() or not 0 <= rating <= MAX_RATING:
            raise ValueError
        if rating != rating.quantize(RATING_STEP):
            raise ValueError
        return rating
    if kind == "relevance":
        # A double compared with a double: relevance is never negative or non-finite.
        if type(key) is not float or not math.isfinite(key) or key < 0:
            raise ValueError
        return key
    if type(key) is not int or not 0 <= key <= PG_BIGINT_MAX:
        raise ValueError
    return key


def decode_cursor(raw: str | None, sort: str) -> tuple[CursorKey, UUID] | None:
    """A cursor from a list without a search."""
    decoded = _decode(raw, sort, searching=False)
    return decoded[0] if decoded else None


def decode_search_cursor(
    raw: str | None, sort: str
) -> tuple[tuple[CursorKey, UUID], SearchMode] | None:
    """A cursor from a search, with the mode its first page chose."""
    decoded = _decode(raw, sort, searching=True)
    if decoded is None or decoded[1] is None:
        return None
    return decoded[0], decoded[1]


def _decode(
    raw: str | None, sort: str, *, searching: bool
) -> tuple[tuple[CursorKey, UUID], SearchMode | None] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if not isinstance(payload, dict) or payload.get("s") != sort:
            raise ValueError
        if searching != ("m" in payload):
            raise ValueError
        mode = SearchMode(payload["m"]) if searching else None
        return (_parse_key(_key_kind(sort), payload["k"]), UUID(payload["i"])), mode
    except (
        ValueError,
        TypeError,
        KeyError,
        InvalidOperation,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        raise bad_query("cursor", "cursor is not a valid pagination cursor") from exc
