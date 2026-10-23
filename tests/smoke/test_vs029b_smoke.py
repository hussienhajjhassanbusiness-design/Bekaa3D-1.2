"""VS-029b smoke suite (receipt confirmation and problem report). Every point is proven by
the slice's own tests, so this file lists them; `tests/conftest.py` marks each."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/ordering/test_receipt_api.py"
_RACES = "tests/concurrency/test_receipt_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    '"I got it" stamps the received lines once and changes no state': [
        f"{_API}::test_confirm_stamps_only_the_received_physical_lines",
        f"{_API}::test_confirming_twice_keeps_the_first_timestamp",
    ],
    "a report reaches the contact queue and every administrator": [
        f"{_API}::test_a_report_queues_a_linked_message_and_stamps_the_received_lines",
        f"{_API}::test_a_report_notifies_every_active_administrator_exactly_once",
    ],
    "nothing received, or not yours: refused with nothing written": [
        f"{_API}::test_an_order_with_nothing_received_refuses_both_actions",
        f"{_API}::test_another_customers_order_and_an_unknown_id_are_the_same_404",
    ],
    "an order completes without confirmation": [
        f"{_API}::test_a_cash_order_completes_through_the_handover_with_no_confirmation"
    ],
    "a confirm racing the handover never deadlocks": [
        f"{_RACES}::test_a_confirm_racing_the_cash_handover_sees_the_lines_it_locked"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs029b_smoke_test_still_exists() -> None:
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


def test_the_vs029b_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
