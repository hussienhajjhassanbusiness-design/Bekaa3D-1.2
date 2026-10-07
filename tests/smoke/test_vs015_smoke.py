"""VS-015 smoke suite (public catalogue). Every point is already proven by the slice's
own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_PRODUCTS = "tests/integration/catalog/test_storefront_products.py"
_SCALE = "tests/integration/catalog/test_storefront_scale.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "hidden, deleted and inactive-category products never show": [
        f"{_PRODUCTS}::test_invisible_products_are_excluded_from_the_list",
        f"{_PRODUCTS}::test_invisible_products_have_no_detail_page",
    ],
    "unavailable products show, marked unavailable": [
        f"{_PRODUCTS}::test_an_unavailable_product_is_listed_and_served_but_marked",
    ],
    "facets combine with AND": [f"{_PRODUCTS}::test_facets_combine_with_and"],
    "the cursor stays stable under inserts": [
        "tests/concurrency/test_storefront_cursor_under_inserts.py"
        "::test_paging_sees_each_existing_product_once_despite_inserts",
    ],
    "browse is under 500 ms p95 on 10,000 products": [
        f"{_SCALE}::test_browse_p95_is_under_500_ms_on_10k_products",
    ],
    "a visitor can browse with no account": [
        f"{_PRODUCTS}::test_anonymous_visitors_can_browse_without_cookies",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs015_smoke_test_still_exists() -> None:
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
