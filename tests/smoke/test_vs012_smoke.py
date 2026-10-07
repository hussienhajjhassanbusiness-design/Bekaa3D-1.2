"""VS-012 smoke suite (012a partitioned audit log + 012b viewer and BUG-39).

Run it alone with `pytest -m smoke` - about 20 seconds. Not deep testing: the
few things that must keep working on the live site, so a break shows at once.

Most of the eight points are already proven by the slice's own tests, so they
are not copied here. `SMOKE_ELSEWHERE` names them, and `tests/conftest.py` adds
the `smoke` marker to each at collection time; one file therefore shows the
whole suite, and `test_every_listed_smoke_test_still_exists` fails the moment a
listed test is renamed or removed, so the suite cannot quietly shrink. Only the
gaps are written below.
"""

import ast
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import client_for, create_user, login, mfa_admin

pytestmark = pytest.mark.smoke

AUDIT_LOGS = "/api/v1/admin/audit-logs"

_PLATFORM = "tests/integration/platform"
_IDENTITY = "tests/integration/identity"

# point -> existing tests that already prove it (node ids without parameters).
SMOKE_ELSEWHERE: dict[str, list[str]] = {
    "partitions exist for the current month and the next three": [
        f"{_PLATFORM}/test_audit_logs_partitioning.py"
        "::test_upgrading_an_empty_table_starts_at_the_current_month",
        f"{_PLATFORM}/test_ensure_partitions.py"
        "::test_at_the_current_time_the_migration_already_covered_everything",
    ],
    "ensure_partitions runs without errors and is safe to run twice": [
        f"{_PLATFORM}/test_ensure_partitions.py::test_a_second_run_creates_nothing",
        f"{_PLATFORM}/test_ensure_partitions.py::test_the_worker_runs_it_monthly_and_at_startup",
    ],
    "a normal action still writes an audit row after partitioning": [
        f"{_PLATFORM}/test_audit_logs_partitioning.py"
        "::test_existing_audit_writes_still_work_end_to_end",
    ],
    "a non-admin or logged-out user cannot open the audit log": [
        f"{_PLATFORM}/test_admin_audit_logs.py::test_an_anonymous_caller_is_told_to_authenticate",
        f"{_PLATFORM}/test_admin_audit_logs.py::test_a_customer_cannot_see_the_audit_log_exists",
    ],
    "viewing the user list and a single user writes an audit row with no email": [
        f"{_IDENTITY}/test_deep_vs009_admin_users.py"
        "::test_the_pii_read_audit_rows_name_the_admin_and_hold_no_pii",
    ],
    "an email search does not appear in the server access log": [
        f"{_IDENTITY}/test_deep_vs009_admin_users.py"
        "::test_an_admin_email_search_never_reaches_the_server_log",
        f"{_IDENTITY}/test_deep_vs009_admin_users.py"
        "::test_an_authenticated_admin_email_search_never_reaches_the_server_log",
    ],
    "contexts reach each other only through public or ports (BUG-41)": [
        "tests/unit/test_deep_architecture.py"
        "::test_no_context_imports_another_contexts_infrastructure",
        "tests/unit/test_deep_architecture.py::test_the_application_layer_depends_on_the_domain_only",
        "tests/unit/test_deep_architecture.py"
        "::test_cross_context_imports_go_only_through_public_or_ports",
    ],
    "the migration runs on a database with data without losing rows": [
        f"{_PLATFORM}/test_audit_logs_partitioning.py"
        "::test_upgrade_down_and_up_again_keeps_every_row_and_restores_the_original_table",
    ],
}

_ROOT = Path(__file__).resolve().parents[2]


def test_every_listed_smoke_test_still_exists() -> None:
    """Static on purpose: it reads the files rather than importing them, so it
    holds however `pytest -m smoke` was narrowed."""
    missing = []
    for node_ids in SMOKE_ELSEWHERE.values():
        for node_id in node_ids:
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


# --------------------------------------------------------------------------
# Gap: the viewer showing a row the application itself wrote. The viewer's own
# tests seed rows directly; nothing yet proved that an ordinary action's audit
# row comes back through the API, in the list and on its own.
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_sees_a_real_login_in_the_audit_log(db_session: AsyncSession) -> None:
    customer = await create_user(db_session)
    customer_id = customer.id
    with client_for(main_app) as customer_client:
        login_request = login(customer_client, customer.email).headers["x-request-id"]

    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        listed = admin.get(AUDIT_LOGS, params={"request_id": login_request})
        assert listed.status_code == 200, listed.text
        [entry] = listed.json()["items"]
        one = admin.get(f"{AUDIT_LOGS}/{entry['id']}")
        missing = admin.get(f"{AUDIT_LOGS}/{uuid.uuid4()}")

    assert entry["action"] == "user.logged_in"
    assert entry["actor_user_id"] == str(customer_id)
    assert entry["request_id"] == login_request
    assert one.status_code == 200, one.text
    assert one.json() == entry
    assert missing.status_code == 404
