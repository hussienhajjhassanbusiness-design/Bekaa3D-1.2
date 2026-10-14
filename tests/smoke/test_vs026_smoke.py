"""VS-026 smoke suite (address book). Every point is already proven by the slice's own
tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/identity/test_addresses_api.py"
_DB = "tests/integration/identity/test_addresses_db.py"
_RACE = "tests/concurrency/test_address_default_race.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a customer saves an address and reads it back normalised": [
        f"{_API}::test_create_normalises_and_returns_the_address"
    ],
    "the first address is the default, later ones are not": [
        f"{_API}::test_first_address_is_default_and_later_ones_are_not"
    ],
    "switching the default leaves one": [
        f"{_API}::test_put_default_switches_atomically_and_is_idempotent",
        f"{_RACE}::test_parallel_switches_leave_one_default",
    ],
    "the database allows one live default per user": [
        f"{_DB}::test_a_second_live_default_is_refused"
    ],
    "another user's address is 404": [
        f"{_API}::test_another_users_address_is_indistinguishable_from_none"
    ],
    "an unverified user cannot write": [f"{_API}::test_an_unverified_user_cannot_write"],
    "invalid Lebanese address data is refused": [
        f"{_API}::test_invalid_create_is_422_and_stores_nothing"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs026_smoke_test_still_exists() -> None:
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


def test_the_vs026_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
