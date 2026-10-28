"""VS-036 plan 6.1: content rules, body shape, rating average, the D14 mask, limits."""

from decimal import Decimal

import pytest

from app.catalog.api.reference_data import PUBLIC_RATE_LIMIT, PUBLIC_RATE_WINDOW_SECONDS
from app.catalog.application.ports import PurchaseMode
from app.engagement.domain import review_limits
from app.engagement.domain.profanity import PROFANITY_WORDS
from app.engagement.domain.reviews import (
    BODY_MAX,
    ContentRefusal,
    badge_shown,
    content_refusal,
    normalise_body,
    rating_average,
)


@pytest.mark.parametrize(
    "body",
    [
        "see http://x",
        "HTTPS://X.COM",
        "go to www.x",
        "buy at x.com today",
        "mail a@b.lb",
        "x\N{FULLWIDTH FULL STOP}com",  # folded to "." by NFKC
        "ftp://files",
        "shop.lb",
    ],
)
def test_links_are_refused(body: str) -> None:
    assert content_refusal(body) is ContentRefusal.LINK


@pytest.mark.parametrize(
    "body",
    ["5.0 stars", "e.g. the finish", "a 3.5mm jack", "Great print!", "came 2 days early."],
)
def test_ordinary_text_is_not_a_link(body: str) -> None:
    assert content_refusal(body) is None


FULLWIDTH_FUCK = "".join(chr(ord(c) + 0xFEE0) for c in "fuck")


@pytest.mark.parametrize(
    "body", ["This is SHIT", "fuck.", f"{FULLWIDTH_FUCK} this", "يا شرموطة", "3ars"]
)
def test_profanity_is_refused_as_a_whole_word_case_and_nfkc_folded(body: str) -> None:
    assert content_refusal(body) is ContentRefusal.PROFANITY


@pytest.mark.parametrize("body", ["Scunthorpe print", "a shitake mushroom lamp", "Dickens fan"])
def test_a_listed_word_inside_a_clean_word_is_not_refused(body: str) -> None:
    assert content_refusal(body) is None


@pytest.mark.parametrize(
    ("body", "refusal"),
    [
        ("visit cheap3d\u200b.com today", ContentRefusal.LINK),  # zero-width space
        ("cheap3d.\ufeffcom", ContentRefusal.LINK),  # BOM / zero-width no-break space
        ("www\u2060.x", ContentRefusal.LINK),  # word joiner
        ("http\u200d://x", ContentRefusal.LINK),  # zero-width joiner
        ("cheap3d\u00ad.com", ContentRefusal.LINK),  # soft hyphen
        ("cheap3d\u3164.com", ContentRefusal.LINK),  # Hangul filler, not category Cf
        ("what a sh\u200bit lamp", ContentRefusal.PROFANITY),
        ("f\u200cu\u200dck", ContentRefusal.PROFANITY),
    ],
)
def test_invisible_characters_cannot_hide_a_link_or_a_word(
    body: str, refusal: ContentRefusal
) -> None:
    assert content_refusal(body) is refusal


def test_text_with_ordinary_joiners_is_still_accepted() -> None:
    assert content_refusal("Great print \U0001f469\u200d\U0001f4bb, 10/10") is None


def test_the_list_is_stored_folded() -> None:
    assert all(word == word.casefold() for word in PROFANITY_WORDS)


def test_a_missing_body_is_never_refused() -> None:
    assert content_refusal(None) is None


def test_whitespace_only_becomes_none_and_text_is_trimmed() -> None:
    assert normalise_body(None) is None
    assert normalise_body(" \n\t ") is None
    assert normalise_body("  nice  ") == "nice"


def test_the_body_limit_counts_after_trim() -> None:
    assert normalise_body("a" * BODY_MAX) == "a" * BODY_MAX
    assert normalise_body(f"  {'a' * BODY_MAX}  ") == "a" * BODY_MAX
    with pytest.raises(ValueError, match="2000"):
        normalise_body("a" * (BODY_MAX + 1))


@pytest.mark.parametrize(
    ("ratings_sum", "count", "expected"),
    [(0, 0, "0.00"), (5, 1, "5.00"), (14, 3, "4.67"), (11, 3, "3.67"), (9, 8, "1.13")],
)
def test_rating_average_rounds_half_up_to_cents(
    ratings_sum: int, count: int, expected: str
) -> None:
    assert rating_average(ratings_sum, count) == Decimal(expected)


@pytest.mark.parametrize("mode", [None, PurchaseMode.ONLINE_ONLY, PurchaseMode.BOTH])
def test_the_badge_shows_unless_the_product_is_whatsapp_only(mode: PurchaseMode | None) -> None:
    assert badge_shown(True, mode)
    assert not badge_shown(False, mode)


def test_a_whatsapp_only_product_never_shows_the_badge() -> None:
    assert not badge_shown(True, PurchaseMode.WHATSAPP_ONLY)


def test_limits_are_the_planned_constants() -> None:
    assert review_limits.REVIEW_WRITE_LIMIT == 10
    assert review_limits.REVIEW_WRITE_WINDOW_SECONDS == 3600
    assert review_limits.REVIEW_READ_LIMIT == PUBLIC_RATE_LIMIT == 600
    assert review_limits.REVIEW_READ_WINDOW_SECONDS == PUBLIC_RATE_WINDOW_SECONDS
