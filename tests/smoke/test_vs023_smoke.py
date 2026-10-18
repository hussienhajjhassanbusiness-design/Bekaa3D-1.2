"""VS-023 smoke suite (digital checkout and verified payment). Every point is already
proven by the slice's own tests, so this file only lists them; `tests/conftest.py`
marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_CHECKOUT = "tests/integration/ordering/test_checkout_api.py"
_WEBHOOK = "tests/integration/payments/test_webhook_api.py"
_VERIFY = "tests/integration/payments/test_verification.py"
_OWNERSHIP = "tests/integration/ordering/test_stl_ownership_api.py"
_E2E = "tests/e2e/test_vs023_digital_purchase.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "checkout answers 201 with a pending payment": [
        f"{_CHECKOUT}::test_checkout_places_a_pending_order_at_the_live_price"
    ],
    "a signed webhook answers 200 and is verified after it": [
        f"{_WEBHOOK}::test_a_signed_event_is_stored_and_verified_after_the_200"
    ],
    "the verify_payments job applies an event": [
        f"{_VERIFY}::test_the_cron_applies_an_event_whose_background_task_was_lost"
    ],
    "ownership is true once paid": [f"{_OWNERSHIP}::test_ownership_follows_the_paid_line_states"],
    "register to owned STL, end to end": [
        f"{_E2E}::test_a_customer_buys_an_stl_and_owns_it_once_the_payment_is_verified"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs023_smoke_test_still_exists() -> None:
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


def test_the_vs023_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
