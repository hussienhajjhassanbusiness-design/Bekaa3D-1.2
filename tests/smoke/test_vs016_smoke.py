"""VS-016 smoke suite (search and autocomplete). Every point is already proven by the
slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_SEARCH = "tests/integration/catalog/test_storefront_search.py"
_SUGGEST = "tests/integration/catalog/test_search_suggestions.py"
_SCALE = "tests/integration/catalog/test_storefront_scale.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a one-typo query finds the product": [
        f"{_SEARCH}::test_one_typo_finds_the_product",
        f"{_SUGGEST}::test_a_partial_or_one_typo_name_is_suggested",
    ],
    "exact and stemmed queries match, names rank above descriptions": [
        f"{_SEARCH}::test_exact_and_stemmed_queries_match",
        f"{_SEARCH}::test_a_name_match_ranks_above_a_description_match_above_a_near_miss",
    ],
    "search never shows hidden, deleted or inactive-category products": [
        f"{_SEARCH}::test_search_never_returns_invisible_products",
    ],
    "SQL-injection strings are harmless": [f"{_SEARCH}::test_injection_strings_are_inert"],
    "an excluded word never comes back": [f"{_SEARCH}::test_an_excluded_word_never_comes_back"],
    "search combines with facets": [f"{_SEARCH}::test_search_combines_with_facets"],
    "suggestions are capped at ten": [f"{_SUGGEST}::test_suggestions_are_capped_at_ten"],
    "search p95 is under 800 ms on 10,000 products": [
        f"{_SCALE}::test_search_p95_is_under_800_ms_on_10k_products",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs016_smoke_test_still_exists() -> None:
    missing = []
    for node_id in (n for ids in SMOKE_ELSEWHERE.values() for n in ids):
        path, _, name = node_id.partition("::")
        source = (_ROOT / path).read_text(encoding="utf-8") if (_ROOT / path).exists() else ""
        defined = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        if name not in defined:
            missing.append(node_id)
    assert not missing, f"listed smoke tests no longer exist: {missing}"


def test_the_vs016_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
