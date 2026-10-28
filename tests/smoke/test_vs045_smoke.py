"""VS-045 smoke suite (account deletion by anonymisation). Every point is proven by the slice's
own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/identity/test_account_deletion.py"
_RACES = "tests/concurrency/test_account_deletion_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a customer deletes their account and no table keeps their personal data": [
        f"{_API}::test_deletion_strips_every_personal_value_from_every_table",
        f"{_API}::test_financial_and_delivery_records_remain_without_personal_data",
    ],
    "the old credentials fail and the email can be registered again": [
        f"{_API}::test_the_old_credentials_and_tokens_no_longer_work",
        f"{_API}::test_the_email_can_be_registered_again",
    ],
    "an open order or an unsettled refund blocks deletion with 409": [
        f"{_API}::test_an_open_order_blocks_and_changes_nothing",
        f"{_API}::test_an_unsettled_refund_blocks_and_changes_nothing",
    ],
    "deletion is all or nothing, and never races a checkout into an order": [
        f"{_API}::test_a_failure_midway_rolls_everything_back",
        f"{_RACES}::test_deletion_first_leaves_a_waiting_cart_checkout_no_account",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs045_smoke_test_still_exists() -> None:
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


def test_the_vs045_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
