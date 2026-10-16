"""VS-038 smoke suite (wishlist). Every point is already proven by the slice's own
tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_WISHLIST = "tests/integration/engagement/test_wishlist_api.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "add, list, remove, list round trip": [f"{_WISHLIST}::test_add_list_remove_list_round_trip"],
    "admin analytics reads totals and most-wishlisted": [
        f"{_WISHLIST}::test_admin_analytics_counts_a_non_public_product"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs038_smoke_test_still_exists() -> None:
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


def test_the_vs038_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
