"""The review lists' keyset cursor over `(created_at, id)` descending (VS-036 plan 2;
shared with the VS-037 admin list). The bytes are part of the public contract."""

import base64
import binascii
from datetime import datetime
from uuid import UUID

from app.engagement.api.queue_cursor import invalid_query, is_utc_representable
from app.engagement.domain.reviews import Review

_SEPARATOR = "|"


def encode_review_cursor(review: Review) -> str:
    raw = f"{review.created_at.isoformat()}{_SEPARATOR}{review.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_review_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        created_raw, id_raw = decoded.split(_SEPARATOR)
        created_at, review_id = datetime.fromisoformat(created_raw), UUID(id_raw)
    except (ValueError, binascii.Error) as exc:
        raise invalid_query("cursor", "cursor is not a valid pagination cursor") from exc
    if not is_utc_representable(created_at):
        raise invalid_query("cursor", "cursor is not a valid pagination cursor")
    return created_at, review_id
