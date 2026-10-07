"""VS-012b: the read-only audit-log viewer behind the VS-005 admin boundary.

`GET /api/v1/admin/audit-logs` and `GET /api/v1/admin/audit-logs/{audit_id}`
(api-endpoints.md 26, 31). Every test seeds its own rows under a unique
`entity_type`, `action`, actor or request id, so the shared test database's other
audit rows never reach an assertion.

Seeded rows sit at and after the start of next month. That partition always
exists (`ensure_partitions` keeps the current month + 3), and it puts the
month-boundary test's earlier rows in this month's partition without depending
on what day the suite runs.
"""

import base64
import uuid
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.enums import UserRole
from app.jobs.partitions import add_months, first_of_month, partition_name
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    login,
    mfa_admin,
)

AUDIT_LOGS = "/api/v1/admin/audit-logs"

READ_FIELDS = {
    "id",
    "actor_user_id",
    "action",
    "entity_type",
    "entity_id",
    "before_data",
    "after_data",
    "request_id",
    "created_at",
}


def _next_month_start() -> datetime:
    return datetime.combine(add_months(first_of_month(datetime.now(UTC)), 1), time(), UTC)


def _tag() -> str:
    return f"test_{uuid.uuid4().hex}"


async def _seed(
    db: AsyncSession,
    *,
    created_at: datetime,
    entity_type: str = "test_entity",
    action: str = "test.seeded",
    actor_user_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    db.add(
        AuditLogModel(
            id=row_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data={"is_active": True},
            after_data={"is_active": False},
            request_id=request_id,
            ip_hash="0" * 64,
            created_at=created_at,
        )
    )
    await db.commit()
    return row_id


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def _walk(client: TestClient, params: dict[str, Any]) -> tuple[list[str], int]:
    """Every id the cursor reaches, in order, and how many pages it took."""
    seen: list[str] = []
    pages = 0
    cursor: str | None = None
    while True:
        response = client.get(
            AUDIT_LOGS, params={**params, **({"cursor": cursor} if cursor else {})}
        )
        seen += _ids(response)
        pages += 1
        cursor = response.json()["next_cursor"]
        if cursor is None:
            return seen, pages
        assert pages < 50, "pagination never terminated"


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_list_is_newest_first_and_never_exposes_the_ip_hash(
    db_session: AsyncSession,
) -> None:
    tag = _tag()
    base = _next_month_start()
    oldest = await _seed(db_session, entity_type=tag, created_at=base + timedelta(minutes=1))
    middle = await _seed(db_session, entity_type=tag, created_at=base + timedelta(minutes=2))
    newest = await _seed(db_session, entity_type=tag, created_at=base + timedelta(minutes=3))

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"entity_type": tag})

    assert _ids(response) == [str(newest), str(middle), str(oldest)]
    body = response.json()
    assert body["next_cursor"] is None
    for item in body["items"]:
        assert set(item) == READ_FIELDS
        assert item["entity_type"] == tag
        assert item["before_data"] == {"is_active": True}
        assert item["after_data"] == {"is_active": False}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_actor_filter_returns_only_that_actors_entries(db_session: AsyncSession) -> None:
    actor = await create_user(db_session, role=UserRole.ADMIN)
    other = await create_user(db_session, role=UserRole.ADMIN)
    base = _next_month_start()
    mine = await _seed(db_session, actor_user_id=actor.id, created_at=base)
    await _seed(db_session, actor_user_id=other.id, created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"actor_user_id": str(actor.id)})

    assert _ids(response) == [str(mine)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_action_filter_matches_the_action_exactly(db_session: AsyncSession) -> None:
    action = f"test.{uuid.uuid4().hex}"
    base = _next_month_start()
    wanted = await _seed(db_session, action=action, created_at=base)
    # A prefix of the action, and the action with a suffix, are different actions.
    await _seed(db_session, action=action[:-1], created_at=base)
    await _seed(db_session, action=f"{action}.more", created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"action": action})

    assert _ids(response) == [str(wanted)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_entity_type_filter_returns_only_that_type(db_session: AsyncSession) -> None:
    tag, other = _tag(), _tag()
    base = _next_month_start()
    wanted = await _seed(db_session, entity_type=tag, created_at=base)
    await _seed(db_session, entity_type=other, created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"entity_type": tag})

    assert _ids(response) == [str(wanted)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_entity_id_filter_returns_only_that_entity(db_session: AsyncSession) -> None:
    entity, other = uuid.uuid4(), uuid.uuid4()
    base = _next_month_start()
    wanted = await _seed(db_session, entity_id=entity, created_at=base)
    await _seed(db_session, entity_id=other, created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"entity_id": str(entity)})

    assert _ids(response) == [str(wanted)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_request_id_filter_returns_only_that_request(db_session: AsyncSession) -> None:
    request_id = f"req_{uuid.uuid4().hex}"
    base = _next_month_start()
    first = await _seed(db_session, request_id=request_id, created_at=base)
    second = await _seed(db_session, request_id=request_id, created_at=base + timedelta(seconds=1))
    await _seed(db_session, request_id=f"req_{uuid.uuid4().hex}", created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"request_id": request_id})

    assert _ids(response) == [str(second), str(first)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_date_range_includes_its_start_and_excludes_its_end(
    db_session: AsyncSession,
) -> None:
    tag = _tag()
    base = _next_month_start()
    t = [base + timedelta(minutes=n) for n in range(4)]
    ids = [await _seed(db_session, entity_type=tag, created_at=moment) for moment in t]

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(
            AUDIT_LOGS,
            params={
                "entity_type": tag,
                "created_after": t[1].isoformat(),
                "created_before": t[3].isoformat(),
            },
        )
        only_after = client.get(
            AUDIT_LOGS, params={"entity_type": tag, "created_after": t[2].isoformat()}
        )
        only_before = client.get(
            AUDIT_LOGS, params={"entity_type": tag, "created_before": t[1].isoformat()}
        )

    assert _ids(response) == [str(ids[2]), str(ids[1])]
    assert _ids(only_after) == [str(ids[3]), str(ids[2])]
    assert _ids(only_before) == [str(ids[0])]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_date_range_means_the_same_instant_in_any_offset(
    db_session: AsyncSession,
) -> None:
    tag = _tag()
    moment = _next_month_start() + timedelta(hours=5)
    wanted = await _seed(db_session, entity_type=tag, created_at=moment)

    beirut = moment.astimezone(timezone(timedelta(hours=3)))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(
            AUDIT_LOGS,
            params={
                "entity_type": tag,
                "created_after": beirut.isoformat(),
                "created_before": (beirut + timedelta(microseconds=1)).isoformat(),
            },
        )

    assert _ids(response) == [str(wanted)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_filters_combine_as_and(db_session: AsyncSession) -> None:
    tag = _tag()
    actor = await create_user(db_session, role=UserRole.ADMIN)
    base = _next_month_start()
    wanted = await _seed(
        db_session, entity_type=tag, actor_user_id=actor.id, action="test.kept", created_at=base
    )
    await _seed(
        db_session, entity_type=tag, actor_user_id=actor.id, action="test.other", created_at=base
    )
    await _seed(db_session, entity_type=tag, action="test.kept", created_at=base)

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(
            AUDIT_LOGS,
            params={"entity_type": tag, "actor_user_id": str(actor.id), "action": "test.kept"},
        )

    assert _ids(response) == [str(wanted)]


# --------------------------------------------------------------------------
# Cursor paging
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_cursor_visits_every_entry_once_even_with_equal_timestamps(
    db_session: AsyncSession,
) -> None:
    """Three of the five rows share one `created_at`, so a cursor without the id
    tie-breaker would skip or repeat them at a page edge."""
    tag = _tag()
    base = _next_month_start()
    moments = [base, base + timedelta(seconds=1), base + timedelta(seconds=1)]
    moments += [base + timedelta(seconds=1), base + timedelta(seconds=2)]
    ids = [await _seed(db_session, entity_type=tag, created_at=moment) for moment in moments]

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        seen, pages = _walk(client, {"entity_type": tag, "limit": 2})
        everything = _ids(client.get(AUDIT_LOGS, params={"entity_type": tag, "limit": 100}))

    assert pages == 3
    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == {str(i) for i in ids}
    assert seen == everything


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_full_last_page_has_no_next_cursor(db_session: AsyncSession) -> None:
    tag = _tag()
    base = _next_month_start()
    for n in range(2):
        await _seed(db_session, entity_type=tag, created_at=base + timedelta(seconds=n))

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params={"entity_type": tag, "limit": 2})

    assert len(_ids(response)) == 2
    assert response.json()["next_cursor"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_query_and_a_cursor_walk_cross_a_month_partition_boundary(
    db_session: AsyncSession,
) -> None:
    tag = _tag()
    boundary = _next_month_start()
    moments = [
        boundary - timedelta(seconds=1),
        boundary - timedelta(microseconds=1),
        boundary,
        boundary + timedelta(seconds=1),
    ]
    ids = [await _seed(db_session, entity_type=tag, created_at=moment) for moment in moments]

    # The rows really are in two partitions, so the reads below cross one.
    placed: dict[str, str] = dict(
        (
            await db_session.execute(
                text(
                    "SELECT id::text, tableoid::regclass::text FROM audit_logs "
                    "WHERE entity_type = :tag"
                ),
                {"tag": tag},
            )
        ).all()
    )
    this_month = partition_name("audit_logs", first_of_month(boundary - timedelta(seconds=1)))
    next_month = partition_name("audit_logs", first_of_month(boundary))
    assert [placed[str(i)] for i in ids] == [this_month, this_month, next_month, next_month]

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        seen, pages = _walk(client, {"entity_type": tag, "limit": 1})
        ranged = client.get(
            AUDIT_LOGS,
            params={
                "entity_type": tag,
                "created_after": moments[0].isoformat(),
                "created_before": moments[3].isoformat(),
            },
        )

    assert seen == [str(i) for i in reversed(ids)]
    assert pages == 4
    assert _ids(ranged) == [str(ids[2]), str(ids[1]), str(ids[0])]


# --------------------------------------------------------------------------
# One entry
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_one_entry_can_be_read_by_id(db_session: AsyncSession) -> None:
    actor = await create_user(db_session, role=UserRole.ADMIN)
    entity = uuid.uuid4()
    moment = _next_month_start() + timedelta(minutes=7)
    row_id = await _seed(
        db_session,
        actor_user_id=actor.id,
        action="test.read_one",
        entity_type="test_entity",
        entity_id=entity,
        request_id="req_read_one",
        created_at=moment,
    )

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(f"{AUDIT_LOGS}/{row_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == READ_FIELDS
    assert body["id"] == str(row_id)
    assert body["actor_user_id"] == str(actor.id)
    assert body["action"] == "test.read_one"
    assert body["entity_type"] == "test_entity"
    assert body["entity_id"] == str(entity)
    assert body["request_id"] == "req_read_one"
    assert datetime.fromisoformat(body["created_at"]) == moment


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_entry_is_404(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(f"{AUDIT_LOGS}/{uuid.uuid4()}")
    assert_problem(response, 404, "NOT_FOUND")


# --------------------------------------------------------------------------
# Bad input is a 422, never a 500 or a silently wrong page
# --------------------------------------------------------------------------


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"cursor": "not-a-cursor!"}, "cursor"),
        ({"cursor": _b64("2026-01-01T00:00:00+00:00")}, "cursor"),
        ({"cursor": _b64(f"2026-01-01T00:00:00|{uuid.uuid4()}")}, "cursor"),
        ({"cursor": _b64(f"0001-01-01T00:00:00+05:00|{uuid.uuid4()}")}, "cursor"),
        ({"created_after": "2026-01-01T00:00:00"}, "created_after"),
        ({"created_before": "2026-01-01T00:00:00"}, "created_before"),
        ({"created_after": "0001-01-01T00:00:00+05:00"}, "created_after"),
        ({"created_before": "9999-12-31T23:59:59-05:00"}, "created_before"),
        (
            {"created_after": "2026-02-01T00:00:00Z", "created_before": "2026-02-01T00:00:00Z"},
            "created_before",
        ),
        (
            {"created_after": "2026-03-01T00:00:00Z", "created_before": "2026-02-01T00:00:00Z"},
            "created_before",
        ),
        ({"actor_user_id": "not-a-uuid"}, "actor_user_id"),
        ({"entity_id": "not-a-uuid"}, "entity_id"),
        ({"limit": "0"}, "limit"),
        ({"limit": "101"}, "limit"),
        ({"action": "x" * 201}, "action"),
        ({"entity_type": "x" * 201}, "entity_type"),
        ({"request_id": "x" * 129}, "request_id"),
    ],
)
async def test_bad_query_parameters_are_a_validation_error(
    db_session: AsyncSession, params: dict[str, str], field: str
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(AUDIT_LOGS, params=params)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert field in str(response.json()["errors"])


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_malformed_entry_id_is_a_validation_error(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(f"{AUDIT_LOGS}/not-a-uuid")
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------
# Admin only, and read only
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [AUDIT_LOGS, f"{AUDIT_LOGS}/{uuid.uuid4()}"])
def test_an_anonymous_caller_is_told_to_authenticate(path: str) -> None:
    with client_for(main_app) as client:
        assert_problem(client.get(path), 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [AUDIT_LOGS, f"{AUDIT_LOGS}/{uuid.uuid4()}"])
async def test_a_customer_cannot_see_the_audit_log_exists(
    db_session: AsyncSession, path: str
) -> None:
    customer = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, customer.email)
        response = client.get(path)
        imaginary = client.get("/api/v1/admin/no-such-thing")
    assert_problem(response, 404, "NOT_FOUND")
    assert response.json()["detail"] == imaginary.json()["detail"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [AUDIT_LOGS, f"{AUDIT_LOGS}/{uuid.uuid4()}"])
async def test_an_administrator_without_mfa_is_refused(db_session: AsyncSession, path: str) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        assert_problem(client.get(path), 401, "MFA_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", [AUDIT_LOGS, f"{AUDIT_LOGS}/{uuid.uuid4()}"])
async def test_the_audit_log_cannot_be_written_through_the_api(
    db_session: AsyncSession, method: str, path: str
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.request(method, path, json={"action": "forged"})
    assert response.status_code == 405, response.text
    assert {m.strip() for m in response.headers["allow"].split(",")} <= {"GET", "HEAD"}
