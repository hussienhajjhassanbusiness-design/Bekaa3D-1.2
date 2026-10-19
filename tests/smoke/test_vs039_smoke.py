"""VS-039 smoke suite (offer submission and inactivity expiry). Every point is already proven
by the slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/negotiation/test_offers_api.py"
_EXPIRY = "tests/integration/negotiation/test_expire_offers.py"
_RACES = "tests/concurrency/test_offer_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a submission opens an offer on the administrator's turn": [
        f"{_API}::test_submit_opens_an_offer_on_the_admins_turn"
    ],
    "one live offer per customer and product, under concurrency": [
        f"{_RACES}::test_concurrent_submissions_leave_one_live_offer"
    ],
    "below the floor is refused": [f"{_API}::test_floor_is_exact"],
    "the kill switch blocks new offers only": [
        f"{_API}::test_kill_switch_refuses_submission_and_writes_nothing",
        f"{_EXPIRY}::test_kill_switch_does_not_stop_expiry",
    ],
    "stale offers expire, once": [
        f"{_EXPIRY}::test_an_overdue_offer_expires_with_a_system_round",
        f"{_RACES}::test_overlapping_expiry_runs_expire_once",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs039_smoke_test_still_exists() -> None:
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


def test_the_vs039_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
