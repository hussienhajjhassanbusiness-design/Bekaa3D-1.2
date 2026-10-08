"""Storefront filter validation, search rules (VS-016) and commerce capabilities (VS-015)."""

from decimal import Decimal

import pytest

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.exceptions import ProductValidationError
from app.catalog.domain.storefront import (
    MAX_SEARCH_LENGTH,
    MIN_FULL_TEXT_HITS,
    MIN_FUZZY_LENGTH,
    MIN_SUGGESTION_LENGTH,
    SearchMode,
    StorefrontFilter,
    StorefrontSort,
    capabilities,
    fuzzy_eligible,
    has_trigram_word,
    resolve_sort,
    search_mode_for,
    search_term,
    search_term_errors,
    suggestion_term_errors,
)

PHYSICAL, STL = ProductType.PHYSICAL, ProductType.STL


def test_an_inverted_price_range_is_refused() -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(price_min_cents=501, price_max_cents=500)
    assert set(caught.value.errors) == {"price_min_cents"}


def test_an_equal_price_range_is_allowed() -> None:
    StorefrontFilter(price_min_cents=500, price_max_cents=500)


@pytest.mark.parametrize("rating", ["-0.01", "5.01"])
def test_min_rating_outside_zero_to_five_is_refused(rating: str) -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(min_rating=Decimal(rating))
    assert set(caught.value.errors) == {"min_rating"}


def test_min_rating_finer_than_the_column_is_refused() -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(min_rating=Decimal("3.994"))
    assert caught.value.errors == {"min_rating": "must have at most 2 decimal places"}


@pytest.mark.parametrize("rating", ["0", "5", "3.5", "3.99", "4.50"])
def test_min_rating_bounds_are_inclusive(rating: str) -> None:
    StorefrontFilter(min_rating=Decimal(rating))


@pytest.mark.parametrize(
    ("product_type", "mode", "available", "cart", "offer", "whatsapp"),
    [
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, True, True, False, False),
        (PHYSICAL, PurchaseMode.BOTH, True, True, False, True),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, True, False, False, True),
        # Unavailable stops on-platform buying only; WhatsApp is off-platform.
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, False, False, False, False),
        (PHYSICAL, PurchaseMode.BOTH, False, False, False, True),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, False, False, False, True),
        (STL, None, True, True, True, False),
        (STL, None, False, False, False, False),
    ],
)
def test_capabilities_follow_type_mode_and_availability(
    product_type: ProductType,
    mode: PurchaseMode | None,
    available: bool,
    cart: bool,
    offer: bool,
    whatsapp: bool,
) -> None:
    derived = capabilities(product_type, mode, available)
    assert (derived.can_add_to_cart, derived.can_offer, derived.whatsapp_available) == (
        cart,
        offer,
        whatsapp,
    )


# ---------------------------------------------------------------- search (VS-016)


@pytest.mark.parametrize(
    ("hits", "mode"),
    [
        (0, SearchMode.FUZZY),
        (MIN_FULL_TEXT_HITS - 1, SearchMode.FUZZY),
        (MIN_FULL_TEXT_HITS, SearchMode.FULL_TEXT),
        (MIN_FULL_TEXT_HITS + 1, SearchMode.FULL_TEXT),
    ],
)
def test_trigram_joins_in_only_below_five_full_text_hits(hits: int, mode: SearchMode) -> None:
    assert MIN_FULL_TEXT_HITS == 5
    assert search_mode_for(hits, eligible=True) is mode


@pytest.mark.parametrize("hits", [0, MIN_FULL_TEXT_HITS - 1, MIN_FULL_TEXT_HITS])
def test_an_ineligible_term_never_falls_back(hits: int) -> None:
    assert search_mode_for(hits, eligible=False) is SearchMode.FULL_TEXT


@pytest.mark.parametrize(
    ("term", "excludes", "eligible"),
    [
        ("s", False, False),
        ("sp", False, False),
        ("spi", False, True),
        ("lamp", False, True),
        ("lamp -moon", True, False),
        ("s s", False, False),
        ("(s)", False, False),
        ("s!!", False, False),
        ("a b c d", False, False),
        ("s sca", False, True),
        ("x-ray", False, True),
    ],
)
def test_typo_matching_needs_three_characters_and_no_excluded_word(
    term: str, excludes: bool, eligible: bool
) -> None:
    assert MIN_FUZZY_LENGTH == MIN_SUGGESTION_LENGTH == 3
    assert fuzzy_eligible(term, excludes_words=excludes) is eligible


@pytest.mark.parametrize(
    ("raw", "term"), [(None, None), ("", None), ("   ", None), ("  lamp ", "lamp")]
)
def test_a_blank_search_box_is_no_search(raw: str | None, term: str | None) -> None:
    assert search_term(raw) == term


@pytest.mark.parametrize(
    ("term", "min_length", "ok"),
    [
        ("a", 1, True),
        ("a", 2, False),
        ("ab", 2, True),
        ("x" * MAX_SEARCH_LENGTH, 1, True),
        ("x" * (MAX_SEARCH_LENGTH + 1), 1, False),
        ("lamp\x00", 1, False),
        ("lamp\x7f", 1, False),
        ("'; DROP TABLE products; --", 1, True),
    ],
)
def test_search_term_bounds(term: str, min_length: int, ok: bool) -> None:
    assert (search_term_errors(term, min_length=min_length) is None) is ok


@pytest.mark.parametrize("q", ["", " lamp", "x" * (MAX_SEARCH_LENGTH + 1), "a\x00b"])
def test_the_filter_refuses_a_search_term_it_cannot_run(q: str) -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(q=q)
    assert set(caught.value.errors) == {"q"}


@pytest.mark.parametrize(
    ("sort", "q", "resolved"),
    [
        (None, None, "-created_at"),
        (None, "lamp", "-relevance"),
        ("price", "lamp", "price"),
        ("-relevance", "lamp", "-relevance"),
    ],
)
def test_relevance_is_the_default_order_of_a_search(
    sort: StorefrontSort | None, q: str | None, resolved: str
) -> None:
    assert resolve_sort(sort, q) == resolved


def test_relevance_without_a_search_is_refused() -> None:
    with pytest.raises(ProductValidationError) as caught:
        resolve_sort("-relevance", None)
    assert set(caught.value.errors) == {"sort"}


@pytest.mark.parametrize(
    ("term", "ok"),
    [("sca", True), ("Café", True), ("ab", False), ("s s", False), ("(s)", False), ("s!!", False)],
)
def test_a_suggestion_needs_a_word_of_three_letters_or_digits(term: str, ok: bool) -> None:
    assert has_trigram_word(term) is ok
    assert (suggestion_term_errors(term) is None) is ok
