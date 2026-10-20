"""VS-040 smoke suite (offer counter, accept, reject, withdraw). Every point is already proven
by the slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_MINE = "tests/integration/negotiation/test_offer_actions_api.py"
_ADMIN = "tests/integration/negotiation/test_admin_offer_actions_api.py"
_JOB = "tests/integration/negotiation/test_offer_checkout_expiry_and_reminders.py"
_RACES = "tests/concurrency/test_offer_action_races.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a whole negotiation runs turn by turn and keeps every round": [
        f"{_ADMIN}::test_a_whole_negotiation_is_kept_round_by_round"
    ],
    "acting out of turn is 409": [
        f"{_MINE}::test_out_of_turn_is_409_and_writes_nothing",
        f"{_ADMIN}::test_out_of_turn_is_409",
    ],
    "the agreed amount never exceeds today's list price": [
        f"{_ADMIN}::test_admin_accept_caps_at_todays_list_price",
        f"{_MINE}::test_accept_caps_the_agreed_amount_at_todays_list_price",
    ],
    "an accept racing a reject: one wins": [f"{_RACES}::test_accept_racing_reject_one_wins"],
    "rejection arms the cooldown; zero means none": [
        f"{_ADMIN}::test_reject_arms_the_cooldown_and_a_resubmission_waits_for_it",
        f"{_ADMIN}::test_with_a_zero_cooldown_the_customer_may_offer_again_at_once",
    ],
    "an accepted offer closes at its checkout window, never from inactivity": [
        f"{_JOB}::test_the_checkout_window_closes_at_its_deadline",
        "tests/integration/negotiation/test_expire_offers.py::test_only_awaiting_offers_expire",
    ],
    "the customer is reminded once before the deadline": [
        f"{_JOB}::test_the_reminder_is_sent_once"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs040_smoke_test_still_exists() -> None:
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


def test_the_vs040_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
