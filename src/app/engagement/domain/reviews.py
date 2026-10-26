"""Review content and rating rules (VS-036 plan 3.1, D9, D14), pure."""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Final

from app.catalog.application.ports import PurchaseMode
from app.engagement.domain.profanity import PROFANITY_WORDS

RATING_MIN: Final = 1
RATING_MAX: Final = 5
BODY_MAX: Final = 2000
BODY_TOO_LONG_MESSAGE: Final = f"must be at most {BODY_MAX} characters"

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


def content_refusal(body: str | None) -> ContentRefusal | None:
    """Links first, then profanity as whole words, both after NFKC and casefold."""
    if body is None:
        return None
    folded = unicodedata.normalize("NFKC", body).casefold()
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
