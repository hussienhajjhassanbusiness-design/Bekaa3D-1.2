"""VS-034 smoke suite (Bring Your Idea submission). Every point is already proven by the
slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/engagement/test_custom_requests_api.py"
_PURGE = "tests/integration/engagement/test_purge_expired_attachments.py"
_REAP = "tests/integration/engagement/test_reap_private_attachments.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a guest request is stored with private, re-encoded images": [
        f"{_API}::test_a_valid_request_is_stored_with_private_reencoded_attachments"
    ],
    "a bad captcha stores nothing": [f"{_API}::test_a_bad_captcha_stores_nothing"],
    "rate limits answer 429": [f"{_API}::test_the_sixth_request_from_one_ip_is_rate_limited"],
    "fake types and malware are rejected with nothing stored": [
        f"{_API}::test_a_fake_image_is_rejected_by_content_and_nothing_is_stored",
        f"{_API}::test_malware_is_detected_and_none_of_the_files_is_stored",
    ],
    "attachments are not publicly reachable": [f"{_API}::test_no_route_serves_attachments"],
    "administrators are notified without contact details": [
        f"{_API}::test_a_submission_notifies_every_active_admin_once_without_contact_details"
    ],
    "expired attachments are purged, file and row": [
        f"{_PURGE}::test_the_purge_deletes_file_and_row_but_keeps_the_lead"
    ],
    "orphaned private uploads are reaped": [
        f"{_REAP}::test_orphans_from_a_failed_commit_are_reaped_and_referenced_files_kept"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs034_smoke_test_still_exists() -> None:
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


def test_the_vs034_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
