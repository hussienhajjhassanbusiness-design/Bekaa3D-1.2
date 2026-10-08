"""Excluded words are read from PostgreSQL's own tsquery text (ADR-023), never a regex on q."""

import pytest

from app.catalog.infrastructure.storefront_query import tsquery_negates


@pytest.mark.parametrize(
    ("tsquery", "negates"),
    [
        ("'lamp' & !'moon'", True),
        ("!'lamp'", True),
        ("'lamp' | !'moon'", True),
        ("'lamp' & !( 'moon' <-> 'lamp' )", True),
        ("'lamp' & 'moon'", False),
        ("'self-wat' <-> 'self' <-> 'water'", False),
        ("'it''s' & 'lamp!'", False),
        ("", False),
    ],
)
def test_only_a_not_operator_outside_a_lexeme_counts(tsquery: str, negates: bool) -> None:
    assert tsquery_negates(tsquery) is negates
