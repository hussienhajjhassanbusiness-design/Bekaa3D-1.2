"""VS-046 smoke suite (security retention, IP-salt rotation). Every point is proven by the
slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_ROTATE = "tests/integration/platform/test_rotate_ip_salt.py"
_PURGE = "tests/integration/identity/test_purge_expired_security_records.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "after rotation the same IP hashes differently and writes keep working": [
        "tests/integration/identity/test_ip_hash_after_rotation.py"
        "::test_a_login_after_rotation_stores_a_different_hash_for_the_same_ip"
    ],
    "a login stores the keyed hash": [
        "tests/integration/identity/test_keyed_ip_hash.py"
        "::test_a_login_stores_the_keyed_hash_in_the_session_and_the_audit_row"
    ],
    "rotation is safe to run twice": [
        f"{_ROTATE}::test_a_second_run_with_the_same_now_is_a_no_op",
        "tests/concurrency/test_ip_salt_rotation_race.py"
        "::test_concurrent_rotations_rotate_exactly_once",
    ],
    "the purge never touches live rows and is idempotent": [
        f"{_PURGE}::test_sessions_go_once_their_end_is_past_retention",
        f"{_PURGE}::test_a_rerun_deletes_nothing_more_of_ours",
    ],
    "both jobs are scheduled": [
        f"{_ROTATE}::test_the_worker_checks_daily_and_at_startup",
        f"{_PURGE}::test_the_worker_runs_it_daily_without_a_startup_run",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs046_smoke_test_still_exists() -> None:
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


def test_the_vs046_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
