"""VS-028 smoke suite (physical checkout, delivery, pickup, cash). Every point is already proven
by the slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_E2E = "tests/e2e/test_vs028_physical_checkout.py"
_API = "tests/integration/ordering/test_physical_checkout_api.py"
_EXCLUDED = "tests/integration/ordering/test_cash_order_exclusions.py"
_RACES = "tests/concurrency/test_cash_checkout_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a new customer places a cash pickup order": [
        f"{_E2E}::test_a_new_customer_places_a_cash_pickup_order"
    ],
    "a mixed delivery order paid online: STL to the queue, physical pending": [
        f"{_E2E}::test_a_new_customer_pays_a_mixed_delivery_order_online",
        f"{_API}::test_a_mixed_delivery_order_paid_online_moves_only_the_stl_line",
    ],
    "a cash order is one transaction with no payment and no provider call": [
        f"{_API}::test_a_cash_order_is_one_transaction_with_no_payment_and_no_provider_call",
        f"{_API}::test_a_failure_after_the_order_insert_leaves_no_order_no_claim_and_the_cart",
    ],
    "cash is refused for STL and mixed carts": [
        f"{_API}::test_cash_is_refused_for_an_stl_only_and_a_mixed_cart_before_any_lock"
    ],
    "a paused shop refuses cash with 503": [
        f"{_API}::test_a_paused_shop_refuses_cash_with_503_and_writes_nothing"
    ],
    "cash refusals never say why, nor whether the account or the phone matched": [
        f"{_API}::test_block_and_open_order_refusals_by_account_or_phone_are_byte_identical"
    ],
    "cash and online orders: release, reconcile and retry never touch cash": [
        f"{_EXCLUDED}::test_release_reconcile_retry_and_admin_release_never_select_a_cash_order"
    ],
    "two accounts with one phone race: one cash order": [
        f"{_RACES}::test_r1_two_accounts_one_phone_place_one_cash_order"
    ],
    "one key in parallel on cash: one order, one replay": [
        f"{_RACES}::test_r2_b_one_key_in_parallel_places_one_cash_order_and_replays_it"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs028_smoke_test_still_exists() -> None:
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


def test_the_vs028_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
