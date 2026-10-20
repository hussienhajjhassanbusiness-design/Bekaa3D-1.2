"""VS-024 smoke suite (payment recovery). Every point is proven by the slice's own tests,
so this file lists them (`tests/conftest.py` marks each `smoke`) and checks the two jobs
are registered and the retry and admin routes are in the OpenAPI snapshot."""

import ast
import json
from pathlib import Path

import pytest

from app.jobs.reconcile_payments import reconcile_payments
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from app.jobs.release_stale_checkouts import release_stale_checkouts

pytestmark = pytest.mark.smoke

_RETRY = "tests/integration/ordering/test_payment_retry_api.py"
_RELEASE = "tests/integration/payments/test_release_job.py"
_RECONCILE = "tests/integration/payments/test_reconcile_job.py"
_ADMIN = "tests/integration/payments/test_admin_payment_routes.py"
_E2E = "tests/e2e/test_vs024_payment_recovery.py"

SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "a failed attempt is retried and paid": [
        f"{_RETRY}::test_a_failed_attempt_is_retried_on_the_same_order_and_then_paid"
    ],
    "the release job releases only on an explicit answer": [
        f"{_RELEASE}::test_an_explicit_answer_releases_the_order",
        f"{_RELEASE}::test_no_explicit_answer_never_releases",
    ],
    "the reconcile job applies a missed callback": [
        f"{_RECONCILE}::test_a_missed_callback_is_applied_in_one_run"
    ],
    "admin reconcile answers 202 before the provider call": [
        f"{_ADMIN}::test_reconcile_answers_202_before_the_provider_is_asked_with_no_transaction_open"
    ],
    "retry, release and admin release, end to end": [
        f"{_E2E}::test_a_failed_payment_is_retried_and_paid",
        f"{_E2E}::test_an_expired_payment_is_released_and_the_stl_bought_again",
        f"{_E2E}::test_a_no_status_order_is_released_by_an_admin_after_the_grace",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]
ROUTES = {
    ("post", "/api/v1/me/orders/{order_id}/payments"),
    ("get", "/api/v1/admin/payments"),
    ("get", "/api/v1/admin/payments/{payment_id}"),
    ("post", "/api/v1/admin/payments/{payment_id}/reconcile"),
    ("post", "/api/v1/admin/payments/{payment_id}/confirm"),
    ("post", "/api/v1/admin/orders/{order_id}/release"),
}


def test_every_listed_vs024_smoke_test_still_exists() -> None:
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


def test_the_vs024_smoke_list_is_wired_into_the_marker() -> None:
    from tests.conftest import _SMOKE_NODE_IDS

    listed = {node_id for ids in SMOKE_ELSEWHERE.values() for node_id in ids}
    assert listed <= _SMOKE_NODE_IDS, f"not marked smoke: {sorted(listed - _SMOKE_NODE_IDS)}"


def test_both_recovery_jobs_are_registered() -> None:
    crons = {job.coroutine for job in CRON_JOBS}
    for job in (reconcile_payments, release_stale_checkouts):
        assert job in FUNCTIONS and job in crons


def test_the_retry_and_admin_routes_are_in_the_openapi_snapshot() -> None:
    paths = json.loads(
        (_ROOT / "docs" / "frontend-handoff" / "openapi.json").read_text(encoding="utf-8")
    )["paths"]
    present = {(method, path) for path, operations in paths.items() for method in operations}
    assert present >= ROUTES, sorted(ROUTES - present)
