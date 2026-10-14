"""VS-033 smoke suite (contact form and captcha). Every point is already proven by the
slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_CONTACT = "tests/integration/engagement/test_contact_messages_api.py"
_AUTH = "tests/integration/identity/test_auth_captcha.py"
_FACTORY = "tests/unit/integrations/test_captcha_factory.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a valid message reaches the queue": [
        f"{_CONTACT}::test_a_valid_message_enters_the_queue_as_new"
    ],
    "a bad captcha stores nothing": [f"{_CONTACT}::test_a_bad_captcha_stores_nothing"],
    "the auth forms refuse a bad captcha the same way for every address": [
        f"{_AUTH}::test_a_refused_captcha_answers_identically_for_every_address_and_writes_nothing",
    ],
    "the fake captcha never runs in production": [
        f"{_FACTORY}::test_anything_else_refuses_to_start",
    ],
    "rate limits answer 429": [
        f"{_CONTACT}::test_the_sixth_message_from_one_ip_is_rate_limited",
        f"{_CONTACT}::test_the_61st_attempt_is_refused_before_the_verifier_is_called",
    ],
    "the queue is admin-only": [
        f"{_CONTACT}::test_visitors_customers_and_unfinished_admins_cannot_reach_the_queue",
    ],
    "status changes are audited": [f"{_CONTACT}::test_a_status_change_is_written_and_audited"],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs033_smoke_test_still_exists() -> None:
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


def test_the_vs033_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
