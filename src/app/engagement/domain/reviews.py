"""Review content and rating rules (VS-036 plan 3.1, D9, D14), pure."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.catalog.application.ports import PurchaseMode
from app.engagement.domain.profanity import PROFANITY_WORDS

RATING_MIN: Final = 1
RATING_MAX: Final = 5
BODY_MAX: Final = 2000
BODY_TOO_LONG_MESSAGE: Final = f"must be at most {BODY_MAX} characters"
# VS-037 D6: the optional hide / restore reason, kept only in the audit row.
MODERATION_REASON_MAX: Final = 500
MODERATION_REASON_TOO_LONG_MESSAGE: Final = f"must be at most {MODERATION_REASON_MAX} characters"

LINK_TLDS: Final = (
    "com",
    "net",
    "org",
    "io",
    "co",
    "me",
    "app",
    "info",
    "biz",
    "lb",
    "xyz",
    "link",
    "ly",
    "gg",
    "to",
)
_LINK = re.compile(
    r"[a-z][a-z0-9+.-]*://"
    r"|\bwww\."
    r"|[^\s@]+@[^\s@]+\.[^\s@]+"
    rf"|\b[a-z0-9-]+\.(?:{'|'.join(LINK_TLDS)})\b"
)
_WORD = re.compile(r"\w+")
# Unicode default-ignorable characters outside category Cf, which `_visible` drops as well.
_IGNORABLE = re.compile(
    "[\u034f\u115f\u1160\u17b4\u17b5\u180b-\u180f\u3164\ufe00-\ufe0f\uffa0\U000e0100-\U000e01ef]"
)
_CENTS: Final = Decimal("0.01")


class ContentRefusal(StrEnum):
    LINK = "link"
    PROFANITY = "profanity"


def normalise_body(raw: str | None) -> str | None:
    """Trimmed text, or None for empty / whitespace-only; ValueError over `BODY_MAX`."""
    if raw is None:
        return None
    body = raw.strip()
    if len(body) > BODY_MAX:
        raise ValueError(BODY_TOO_LONG_MESSAGE)
    return body or None


def normalise_reason(raw: str | None) -> str | None:
    """VS-037 D6: trimmed, None for empty / whitespace-only; ValueError over the max."""
    if raw is None:
        return None
    reason = raw.strip()
    if len(reason) > MODERATION_REASON_MAX:
        raise ValueError(MODERATION_REASON_TOO_LONG_MESSAGE)
    return reason or None


def _visible(text: str) -> str:
    """Without zero-width, joiner and bidi characters, which could hide a link or a word."""
    return _IGNORABLE.sub("", "".join(c for c in text if unicodedata.category(c) != "Cf"))


def content_refusal(body: str | None) -> ContentRefusal | None:
    """Links first, then profanity as whole words, on the visible text after NFKC and
    casefold."""
    if body is None:
        return None
    folded = unicodedata.normalize("NFKC", _visible(body)).casefold()
    if _LINK.search(folded):
        return ContentRefusal.LINK
    if any(word in PROFANITY_WORDS for word in _WORD.findall(folded)):
        return ContentRefusal.PROFANITY
    return None


def rating_average(ratings_sum: int, count: int) -> Decimal:
    """Half-up to 0.01; 0.00 with no reviews (the column's own default)."""
    if count == 0:
        return Decimal("0.00")
    return (Decimal(ratings_sum) / Decimal(count)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def badge_shown(stored: bool, purchase_mode: PurchaseMode | None) -> bool:
    """D14 (Q3): a WhatsApp-only product never shows the badge; the stored fact is kept."""
    return stored and purchase_mode is not PurchaseMode.WHATSAPP_ONLY


# int4 namespace of the per-user two-int advisory lock `R_user` (plan 3.2b, D6): "REVW".
REVIEW_LOCK_NS: Final = 0x52455657


@dataclass(frozen=True)
class Review:
    id: UUID
    user_id: UUID
    product_id: UUID
    rating: int
    body: str | None
    is_verified_purchase: bool
    is_hidden: bool
    hidden_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def edited(self) -> bool:
        return self.updated_at > self.created_at


@dataclass(frozen=True)
class NewReview:
    user_id: UUID
    product_id: UUID
    rating: int
    body: str | None
    is_verified_purchase: bool
