"""VS-035 smoke suite (Bring Your Idea pipeline and funnel). Every point is already proven by
the slice's own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_API = "tests/integration/engagement/test_custom_request_admin_api.py"
_DOWNLOAD = "tests/integration/engagement/test_custom_request_attachment_download.py"
_FUNNEL = "tests/integration/engagement/test_custom_request_funnel.py"
_RACE = "tests/concurrency/test_custom_request_transition_race.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a lead walks the whole pipeline, audited, and is recorded as won": [
        f"{_API}::test_a_lead_walks_the_whole_pipeline_and_every_step_is_audited"
    ],
    "an illegal transition is 409": [
        f"{_API}::test_an_illegal_transition_is_409_and_writes_nothing"
    ],
    "only an MFA-complete administrator reaches the pipeline": [
        f"{_API}::test_visitors_customers_and_unfinished_admins_cannot_reach_the_pipeline"
    ],
    "an attachment downloads as an inert, uncached attachment": [
        f"{_DOWNLOAD}::test_the_download_streams_the_exact_bytes_as_an_inert_attachment"
    ],
    "an expired attachment cannot be downloaded": [
        f"{_DOWNLOAD}::test_an_expired_attachment_cannot_be_downloaded"
    ],
    "two admins racing on one lead cannot both commit": [
        f"{_RACE}::test_two_admins_racing_on_one_lead_leave_a_true_audit_chain"
    ],
    "the funnel counts won and lost leads by cohort": [
        f"{_FUNNEL}::test_funnel_counts_match_seeded_data_and_respect_the_cohort_bounds"
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs035_smoke_test_still_exists() -> None:
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


def test_the_vs035_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"
