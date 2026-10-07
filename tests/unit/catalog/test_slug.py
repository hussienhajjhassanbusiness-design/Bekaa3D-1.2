"""Slug normalisation and validation.

Pure domain, no database. The database's partial unique index is the authority
on *uniqueness*; this is the authority on what a slug may look like at all, and
the rules are a VS-010 decision rather than an inherited convention - the
project had no slug code before this slice.
"""

import pytest

from app.catalog.domain.exceptions import InvalidSlugError
from app.catalog.domain.slug import MAX_SLUG_LENGTH, normalise_slug


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("lamps", id="single-word"),
        pytest.param("desk-lamps", id="hyphenated"),
        pytest.param("3d-printed-parts", id="leading-digit"),
        pytest.param("a", id="single-character"),
        pytest.param("part-2-of-3", id="digits-between-hyphens"),
    ],
)
def test_a_well_formed_slug_is_returned_unchanged(raw: str) -> None:
    assert normalise_slug(raw) == raw


def test_surrounding_whitespace_and_case_are_normalised() -> None:
    """Normalisation, not just validation: otherwise `" Lamps "` and `"lamps"`
    are two different stored values for one slug, and the unique index would
    happily accept both."""
    assert normalise_slug("  Desk-Lamps  ") == "desk-lamps"
    assert normalise_slug("LAMPS") == "lamps"


def test_it_is_not_a_slugifier() -> None:
    """Deliberate: `CategoryCreate` carries an explicit `slug` next to `name`,
    so the administrator chooses the URL. Silently rewriting `"Desk Lamps"` into
    `"desk-lamps"` would mean the slug they were shown is not the slug stored."""
    with pytest.raises(InvalidSlugError):
        normalise_slug("Desk Lamps")


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace-only"),
        pytest.param("-lamps", id="leading-hyphen"),
        pytest.param("lamps-", id="trailing-hyphen"),
        pytest.param("desk--lamps", id="double-hyphen"),
        pytest.param("desk lamps", id="space"),
        pytest.param("desk_lamps", id="underscore"),
        pytest.param("desk/lamps", id="slash"),
        pytest.param("desk.lamps", id="dot"),
        pytest.param("lámpara", id="non-ascii"),
        pytest.param("Desk-Lamps!", id="punctuation"),
    ],
)
def test_malformed_slugs_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidSlugError):
        normalise_slug(raw)


def test_length_is_bounded_after_trimming() -> None:
    assert normalise_slug("a" * MAX_SLUG_LENGTH) == "a" * MAX_SLUG_LENGTH
    with pytest.raises(InvalidSlugError):
        normalise_slug("a" * (MAX_SLUG_LENGTH + 1))


def test_a_non_string_is_rejected_rather_than_coerced() -> None:
    with pytest.raises(InvalidSlugError):
        normalise_slug(7)  # type: ignore[arg-type]


def test_the_error_carries_the_original_input_and_a_reason() -> None:
    """An administrator fixing a slug should be told what was wrong with the
    value they actually sent, not with its normalised form."""
    with pytest.raises(InvalidSlugError) as raised:
        normalise_slug("Desk Lamps")
    assert raised.value.slug == "Desk Lamps"
    assert raised.value.reason
