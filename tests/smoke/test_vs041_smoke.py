"""VS-041 smoke suite (accepted-offer checkout and auto-close). Every point is already proven
by the slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/ordering/test_offer_checkout_api.py"
_SETTLE = "tests/integration/negotiation/test_offer_settlement.py"
_RACES = "tests/concurrency/test_offer_checkout_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "negotiate, accept, pay: the offer closes as paid (SRS 5.4)": [
        "tests/integration/negotiation/test_offer_checkout_e2e.py"
        "::test_negotiate_accept_pay_and_close_the_offer_as_paid"
    ],
    "the agreed price is charged whatever the list price": [
        f"{_API}::test_checkout_charges_the_agreed_price_whatever_the_list_price"
    ],
    "after the checkout window: 410": [f"{_API}::test_the_window_closes_at_its_deadline"],
    "a paused shop refuses offer checkout with 503": [
        f"{_API}::test_a_paused_shop_is_503_and_writes_nothing"
    ],
    "a second checkout while a payment is live: 409": [
        f"{_API}::test_a_second_checkout_while_a_payment_is_live_is_409_payment_already_active"
    ],
    "buying through the cart auto-closes the offer": [
        f"{_SETTLE}::test_buying_through_the_cart_auto_closes_a_live_offer"
    ],
    "a payment in flight completes after the window": [
        f"{_SETTLE}::test_the_job_leaves_an_offer_whose_payment_is_in_flight"
    ],
    "offer checkout racing cart checkout: one owning line": [
        f"{_RACES}::test_offer_checkout_racing_cart_checkout_yields_one_owning_line"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs041_smoke_test_still_exists() -> None:
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


def test_the_vs041_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
