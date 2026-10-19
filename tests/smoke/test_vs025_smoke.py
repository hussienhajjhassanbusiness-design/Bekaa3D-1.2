"""VS-025 smoke suite (customer order history). Every point is already proven by the
slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_HISTORY = "tests/integration/ordering/test_order_history_api.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "the detail shows what checkout charged, after product edits": [
        f"{_HISTORY}::test_detail_shows_what_checkout_charged_and_survives_product_edits"
    ],
    "another customer's order is 404": [
        f"{_HISTORY}::test_another_users_order_is_404_like_an_unknown_one"
    ],
    "the admin note and provider references never appear": [
        f"{_HISTORY}::test_internal_fields_never_appear"
    ],
    "pages are stable": [f"{_HISTORY}::test_pages_cover_every_order_once_when_placed_at_ties"],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs025_smoke_test_still_exists() -> None:
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


def test_the_vs025_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
