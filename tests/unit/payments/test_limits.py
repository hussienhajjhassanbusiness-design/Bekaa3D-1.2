"""Every payment-path timing and limit lives in `app.payments.domain.limits` (VS-024 plan
3.8, D14): the values, and a scan for numeric limits defined anywhere else."""

import ast
import re
from datetime import timedelta
from pathlib import Path

from app.payments.domain import limits

SRC = Path(__file__).resolve().parents[3] / "src" / "app"
# Payment-path modules; any module-level numeric limit in them must come from `limits`.
SCANNED = [
    *sorted((SRC / "payments").rglob("*.py")),
    SRC / "ordering" / "api" / "checkout.py",
]
LIMIT_NAME = re.compile(r"(TIMEOUT|LIMIT|BATCH|WINDOW|TTL|MAX_BODY|GRACE|AGE|DEADLINE|PAGE)")
EXPECTED = {
    "PROVIDER_TIMEOUT_SECONDS": 10.0,
    "MOCK_REDIS_TIMEOUT_SECONDS": 10.0,
    "MOCK_STATE_TTL_SECONDS": 7 * 24 * 3600,
    "WEBHOOK_MAX_BODY_BYTES": 64 * 1024,
    "WEBHOOK_UNVERIFIED_LIMIT": 30,
    "WEBHOOK_VERIFIED_LIMIT": 600,
    "WEBHOOK_WINDOW_SECONDS": 60,
    "VERIFY_BATCH_SIZE": 50,
    "RECONCILE_MIN_AGE": timedelta(minutes=5),
    "RECONCILE_PAGE_SIZE": 50,
    "RELEASE_PAGE_SIZE": 50,
    "RECONCILE_CRON_MINUTES": frozenset({0, 15, 30, 45}),
    "RECONCILE_CRON_SECOND": 30,
    "RELEASE_CRON_MINUTES": frozenset(range(2, 60, 5)),
    "RELEASE_CRON_SECOND": 45,
    "JOB_RUN_DEADLINE_SECONDS": 240.0,
    "PROVIDER_BREAKER_FAILURES": 3,
    "STUCK_AFTER": timedelta(hours=1),
    "MANUAL_RELEASE_GRACE": timedelta(hours=24),
    "ALERT_REPEAT_PER_PAYMENT": timedelta(hours=24),
    "ALERT_REPEAT_PER_PROVIDER": timedelta(hours=1),
    "CHECKOUT_RATE_LIMIT": 30,
    "CHECKOUT_RATE_WINDOW_SECONDS": 3600,
    "RETRY_RATE_LIMIT": 10,
    "RETRY_RATE_WINDOW_SECONDS": 3600,
    "CONFIRM_RATE_LIMIT": 30,
    "RECONCILE_RATE_LIMIT": 60,
    "RELEASE_RATE_LIMIT": 30,
    "ADMIN_ACTION_WINDOW_SECONDS": 3600,
    "ADMIN_PAGE_DEFAULT": 20,
    "ADMIN_PAGE_MAX": 100,
    "REASON_MIN": 10,
    "REASON_MAX": 1000,
}


def test_every_limit_has_its_planned_value() -> None:
    public = {name: getattr(limits, name) for name in dir(limits) if name.isupper()}
    assert public == EXPECTED


def test_the_release_job_runs_every_five_minutes_and_reconcile_every_fifteen() -> None:
    assert sorted(limits.RELEASE_CRON_MINUTES) == list(range(2, 60, 5))
    assert len(limits.RECONCILE_CRON_MINUTES) == 4


def test_the_job_deadline_stays_under_arqs_default_job_timeout() -> None:
    assert limits.JOB_RUN_DEADLINE_SECONDS < 300


def _numeric(node: ast.expr) -> bool:
    return any(
        isinstance(sub, ast.Constant) and isinstance(sub.value, int | float)
        for sub in ast.walk(node)
    ) and not any(isinstance(sub, ast.Name) for sub in ast.walk(node))


def test_no_payment_path_module_defines_a_numeric_limit_of_its_own() -> None:
    found: list[str] = []
    for path in SCANNED:
        if path.name == "limits.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            if any(LIMIT_NAME.search(name) for name in names) and _numeric(node.value):
                found.append(f"{path.relative_to(SRC)}:{node.lineno} {names}")
    assert found == []
