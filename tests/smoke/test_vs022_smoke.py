"""VS-022 smoke suite (mixed cart). Every point is already proven by the slice's own
tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/ordering/test_cart_api.py"
_RACES = "tests/concurrency/test_cart_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "add physical and STL, read, patch, delete, read": [
        f"{_API}::test_add_read_patch_delete_round_trip"
    ],
    "an unverified user reads but cannot write": [
        f"{_API}::test_an_unverified_user_reads_an_empty_cart_and_cannot_write"
    ],
    "two concurrent adds stay within the cap": [
        f"{_RACES}::test_two_concurrent_adds_of_one_product_stay_within_the_cap"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs022_smoke_test_still_exists() -> None:
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


def test_the_vs022_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
