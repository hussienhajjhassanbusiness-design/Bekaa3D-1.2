"""VS-044 smoke suite (customer data export). Every point is proven by the slice's own tests,
so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/reporting/test_data_export_api.py"
_SESSION = "tests/integration/reporting/test_data_export_session.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a verified customer downloads the profile and the six data sets": [
        f"{_API}::test_the_export_is_the_profile_and_exactly_the_six_sets"
    ],
    "only the caller's rows, and no internal value, are exported": [
        f"{_API}::test_only_the_callers_rows_appear_in_either_direction",
        f"{_API}::test_no_hash_secret_internal_note_or_provider_reference_is_exported",
    ],
    "an unverified customer is refused and a fourth export in a day is 429": [
        f"{_API}::test_anonymous_is_401_and_unverified_is_403_spending_no_budget",
        f"{_API}::test_three_a_day_per_user_then_429_with_retry_after",
    ],
    "each export is audited, and a failed one is a 503 with no audit row": [
        f"{_API}::test_each_export_writes_one_audit_row_with_no_data",
        f"{_SESSION}::test_a_statement_timeout_on_the_first_read_is_503_with_no_audit_row",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs044_smoke_test_still_exists() -> None:
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


def test_the_vs044_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
