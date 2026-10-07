"""VS-014 smoke suite (product images). Every point is already proven by the slice's
own tests, so this file only lists them; `tests/conftest.py` marks each `smoke`."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_IMAGES = "tests/integration/catalog/test_admin_product_images.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "an uploaded image is stored re-encoded, never as sent": [
        f"{_IMAGES}::test_a_stored_file_is_the_reencoded_output_never_the_upload",
    ],
    "a non-image or malware upload is refused and stores nothing": [
        f"{_IMAGES}::test_the_content_not_the_name_decides_and_rejects",
        f"{_IMAGES}::test_malware_is_detected_on_the_raw_upload",
    ],
    "uploads fail closed when the scanner is down": [
        f"{_IMAGES}::test_an_unavailable_scanner_refuses_the_upload",
    ],
    "a product never has two covers": [
        "tests/integration/catalog/test_product_image_schema.py::test_two_live_covers_are_refused",
        "tests/concurrency/test_product_image_races.py"
        "::test_concurrent_cover_changes_leave_exactly_one_cover",
    ],
    "orphan files are cleaned up": [
        "tests/integration/catalog/test_reap_orphan_files.py"
        "::test_an_orphan_from_a_failed_commit_is_reaped_after_the_grace_period",
    ],
    "non-administrators cannot reach the image routes": [
        f"{_IMAGES}::test_non_admins_get_the_boundary_answers_and_csrf_is_required",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_vs014_smoke_test_still_exists() -> None:
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
