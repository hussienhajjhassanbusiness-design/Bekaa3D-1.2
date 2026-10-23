"""VS-029 smoke suite (admin order queue, fulfillment, cash handover, cash blocks). Every point
is proven by the slice's own tests, so this file lists them; `tests/conftest.py` marks each."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_E2E = "tests/e2e/test_vs029_admin_fulfillment.py"
_MOVE = "tests/integration/fulfillment/test_line_transition_api.py"
_HANDOVER = "tests/integration/fulfillment/test_cash_handover_api.py"
_QUEUE = "tests/integration/fulfillment/test_admin_order_queue_api.py"
_BLOCKS = "tests/integration/ordering/test_admin_cash_blocks_api.py"
_RACES = "tests/concurrency/test_admin_order_races.py"
_STATIC = "tests/unit/payments/test_cash_payment_writers.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a cash pickup order and an online delivery order reach completed": [
        f"{_E2E}::test_a_cash_pickup_order_is_printed_handed_over_and_completed",
        f"{_E2E}::test_a_delivery_order_paid_online_is_moved_to_delivered_and_completed",
    ],
    "no physical work on an unpaid online order, and the queue never lists it": [
        f"{_MOVE}::test_no_physical_work_on_an_unpaid_online_order",
        f"{_QUEUE}::test_the_queue_never_lists_an_unpaid_online_order",
    ],
    "start printing is silent and masked; one notice per order per step": [
        f"{_MOVE}::test_start_printing_is_silent_masked_and_closes_self_cancel",
        f"{_MOVE}::test_a_three_line_delivery_order_hears_once_per_step_on_the_last_line",
    ],
    "available_actions matches the endpoint": [
        f"{_MOVE}::test_every_listed_action_succeeds_and_every_other_target_is_a_409"
    ],
    "the handover: one paid cash payment for the live total, or nothing": [
        f"{_HANDOVER}::test_the_handover_completes_the_order_with_one_paid_cash_payment",
        f"{_HANDOVER}::test_a_wrong_amount_is_a_422_and_changes_nothing",
        f"{_HANDOVER}::test_a_line_not_yet_ready_is_a_409_and_changes_nothing",
    ],
    "only the handover creates a cash payment": [
        f"{_STATIC}::test_only_the_handover_route_reaches_the_cash_insert"
    ],
    "two admins on one handover: one payment": [
        f"{_RACES}::test_two_administrators_recording_one_handover_record_one_payment"
    ],
    "a cleared block lets the customer pay cash again": [
        f"{_BLOCKS}::test_after_clearing_checkout_offers_cash_again_by_account_and_phone"
    ],
    "the internal note never reaches the customer": [
        f"{_QUEUE}::test_the_internal_note_is_never_visible_to_the_customer"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs029_smoke_test_still_exists() -> None:
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


def test_the_vs029_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
