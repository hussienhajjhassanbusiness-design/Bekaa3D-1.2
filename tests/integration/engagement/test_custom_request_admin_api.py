"""VS-035 / FR-15, BR-113, BR-114: the administrator's Bring Your Idea pipeline."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.engagement.infrastructure.models import CustomRequestModel
from app.integrations.storage.factory import get_private_upload_storage
from app.integrations.storage.local import LocalStorage
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    unique_email,
)
from tests.integration.engagement.custom_request_support import seed_lead

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ADMIN = "/api/v1/admin/custom-requests"
FUNNEL = "/api/v1/admin/analytics/custom-requests/funnel"
PNG = b"\x89PNG-private-bytes"


@pytest.fixture
def private(tmp_path: Path) -> Iterator[LocalStorage]:
    storage = LocalStorage(tmp_path / "private")
    main_app.dependency_overrides[get_private_upload_storage] = lambda: storage
    yield storage
    main_app.dependency_overrides.pop(get_private_upload_storage, None)


async def _audits(db: AsyncSession, entity_id: uuid.UUID | None, action: str) -> list[Any]:
    db.expire_all()
    stmt = select(AuditLogModel).where(AuditLogModel.action == action)
    if entity_id is not None:
        stmt = stmt.where(AuditLogModel.entity_id == entity_id)
    return list((await db.scalars(stmt.order_by(AuditLogModel.created_at))).all())


async def _row(db: AsyncSession, request_id: uuid.UUID) -> CustomRequestModel:
    db.expire_all()
    row = await db.get(CustomRequestModel, request_id)
    assert row is not None
    return row


def _move(client: Any, request_id: uuid.UUID, target: str, **extra: Any) -> Any:
    body = {"target_status": target, **extra}
    return client.post(f"{ADMIN}/{request_id}/transition", json=body, headers=csrf(client))


# --------------------------------------------------------------------------
# Boundary
# --------------------------------------------------------------------------

ROUTES = [
    pytest.param("GET", "{admin}", id="list"),
    pytest.param("GET", "{admin}/{id}", id="detail"),
    pytest.param("PATCH", "{admin}/{id}", id="notes"),
    pytest.param("POST", "{admin}/{id}/transition", id="transition"),
    pytest.param("GET", "{admin}/{id}/attachments/{aid}/download", id="download"),
    pytest.param("GET", FUNNEL, id="funnel"),
]
_ANY_BODY = {"target_status": "contacted", "admin_notes": "x"}


@pytest.mark.parametrize(("method", "template"), ROUTES)
async def test_visitors_customers_and_unfinished_admins_cannot_reach_the_pipeline(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    private: LocalStorage,
    method: str,
    template: str,
) -> None:
    lead = await seed_lead(
        db_engine, private, email=unique_email("boundary"), images=[("a.png", PNG)]
    )
    path = template.format(admin=ADMIN, id=lead.id, aid=lead.attachments[0].id)
    customer = await create_user(db_session)
    no_mfa = await create_user(db_session, role="admin")  # type: ignore[arg-type]
    with client_for(main_app) as client:
        assert_problem(client.request(method, path, json=_ANY_BODY), 401, "AUTH_REQUIRED")
        login(client, customer.email)
        response = client.request(method, path, json=_ANY_BODY, headers=csrf(client))
        assert_problem(response, 404, "NOT_FOUND")
        client.cookies.clear()
        login(client, no_mfa.email)
        response = client.request(method, path, json=_ANY_BODY, headers=csrf(client))
        assert_problem(response, 401, "MFA_REQUIRED")
    row = await _row(db_session, lead.id)
    assert (row.status, row.admin_notes) == ("new", None)
    assert PNG not in response.content


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        pytest.param("PATCH", "", {"admin_notes": "x"}, id="notes"),
        pytest.param("POST", "/transition", {"target_status": "contacted"}, id="transition"),
    ],
)
async def test_writes_require_csrf(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    private: LocalStorage,
    method: str,
    suffix: str,
    body: dict[str, Any],
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("csrf"))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.request(method, f"{ADMIN}/{lead.id}{suffix}", json=body)
    assert_problem(response, 403, "CSRF_INVALID")
    row = await _row(db_session, lead.id)
    assert (row.status, row.admin_notes) == ("new", None)


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        pytest.param("GET", "", None, id="detail"),
        pytest.param("PATCH", "", {"admin_notes": "x"}, id="notes"),
        pytest.param("POST", "/transition", {"target_status": "contacted"}, id="transition"),
    ],
)
async def test_an_unknown_request_is_404_and_unaudited(
    db_session: AsyncSession, method: str, suffix: str, body: dict[str, Any] | None
) -> None:
    missing = uuid.uuid4()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.request(
            method, f"{ADMIN}/{missing}{suffix}", json=body, headers=csrf(client)
        )
    assert_problem(response, 404, "NOT_FOUND")
    db_session.expire_all()
    stmt = select(AuditLogModel).where(AuditLogModel.entity_id == missing)
    assert await db_session.scalar(stmt) is None


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


async def test_a_lead_walks_the_whole_pipeline_and_every_step_is_audited(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    """Done-when: every lead follows the state machine; the win is recorded (BR-114)."""
    lead = await seed_lead(db_engine, private, email=unique_email("walk"))
    steps = ["contacted", "quoted", "in_progress", "completed", "closed"]
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        for target in steps:
            extra = {"quoted_amount_cents": 12_500} if target == "quoted" else {}
            response = _move(client, lead.id, target, **extra)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == target
    body = response.json()
    assert (body["outcome"], body["quoted_amount_cents"], body["currency"]) == (
        "won",
        12_500,
        "USD",
    )
    stamps = [body[f] for f in ("contacted_at", "quoted_at", "completed_at", "closed_at")]
    assert all(stamps) and stamps == sorted(stamps)
    audits = await _audits(db_session, lead.id, "custom_request.transitioned")
    assert [(a.before_data["status"], a.after_data["status"]) for a in audits] == list(
        zip(["new", *steps[:-1]], steps, strict=True)
    )
    assert {(a.actor_user_id, a.entity_type) for a in audits} == {(admin_id, "custom_request")}
    assert audits[2].after_data == {
        "status": "in_progress",
        "outcome": "won",
        "quoted_amount_cents": 12_500,
        "currency": "USD",
    }


@pytest.mark.parametrize("source", ["contacted", "quoted"])
async def test_lost_records_the_outcome_and_the_closing_time(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage, source: str
) -> None:
    quote: dict[str, Any] = (
        {"quoted_amount_cents": 900, "currency": "USD"} if source == "quoted" else {}
    )
    lead = await seed_lead(db_engine, private, email=unique_email("lost"), status=source, **quote)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _move(client, lead.id, "lost")
    assert response.status_code == 200, response.text
    row = await _row(db_session, lead.id)
    assert (row.status, row.outcome) == ("lost", "lost")
    assert row.closed_at is not None
    assert row.quoted_amount_cents == quote.get("quoted_amount_cents")


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("new", "quoted"),
        ("new", "lost"),
        ("contacted", "contacted"),
        ("contacted", "in_progress"),
        ("in_progress", "lost"),
        ("closed", "new"),
        ("lost", "contacted"),
        ("completed", "in_progress"),
    ],
)
async def test_an_illegal_transition_is_409_and_writes_nothing(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    private: LocalStorage,
    current: str,
    target: str,
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("illegal"), status=current)
    before = await _row(db_session, lead.id)
    updated_at = before.updated_at
    extra = {"quoted_amount_cents": 100} if target == "quoted" else {}
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _move(client, lead.id, target, **extra)
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    row = await _row(db_session, lead.id)
    assert (row.status, row.updated_at, row.outcome) == (current, updated_at, None)
    assert await _audits(db_session, lead.id, "custom_request.transitioned") == []


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"target_status": "quoted"}, id="quote-missing"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": 0}, id="zero"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": -1}, id="negative"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": 100_000_001}, id="huge"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": 12.5}, id="float"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": "100"}, id="string"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": True}, id="bool"),
        pytest.param({"target_status": "lost", "quoted_amount_cents": 100}, id="misplaced"),
        pytest.param({"target_status": "lost", "outcome": "won"}, id="client-outcome"),
        pytest.param({"target_status": "lost", "note": "x"}, id="note"),
        pytest.param({"target_status": "quoted", "quoted_amount_cents": 1, "currency": "EUR"}),
        pytest.param({"target_status": "spam"}, id="unknown-status"),
        pytest.param({}, id="empty"),
    ],
)
async def test_a_malformed_transition_is_422_and_writes_nothing(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage, body: dict[str, Any]
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("bad"), status="contacted")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(f"{ADMIN}/{lead.id}/transition", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    row = await _row(db_session, lead.id)
    assert (row.status, row.quoted_amount_cents) == ("contacted", None)


async def test_quote_bounds_are_accepted_at_both_ends(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    leads = [
        await seed_lead(db_engine, private, email=unique_email("bound"), status="contacted")
        for _ in range(2)
    ]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        for lead, amount in zip(leads, (1, 100_000_000), strict=True):
            response = _move(client, lead.id, "quoted", quoted_amount_cents=amount)
            assert response.status_code == 200, response.text
            assert response.json()["quoted_amount_cents"] == amount


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


async def test_notes_are_saved_cleared_and_audited_without_their_text(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("notes"), status="quoted")
    sentinel = f"called back, wants walnut {uuid.uuid4().hex}"
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        saved = client.patch(
            f"{ADMIN}/{lead.id}",
            json={"admin_notes": f"  {sentinel}\nline 2 "},
            headers=csrf(client),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["admin_notes"] == f"{sentinel}\nline 2"
        assert saved.json()["status"] == "quoted"
        cleared = client.patch(
            f"{ADMIN}/{lead.id}", json={"admin_notes": "   "}, headers=csrf(client)
        )
        assert cleared.json()["admin_notes"] is None
    audits = await _audits(db_session, lead.id, "custom_request.notes_updated")
    assert [(a.before_data, a.after_data) for a in audits] == [
        ({"has_notes": False}, {"has_notes": True}),
        ({"has_notes": True}, {"has_notes": False}),
    ]
    assert sentinel not in str([(a.before_data, a.after_data) for a in audits])


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"admin_notes": "x" * 5001}, id="too-long"),
        pytest.param({"admin_notes": "a\x00b"}, id="control-character"),
        pytest.param({"admin_notes": "x", "status": "closed"}, id="status"),
        pytest.param({"status": "closed"}, id="status-only"),
        pytest.param({"admin_notes": "x", "quoted_amount_cents": 5}, id="quote"),
        pytest.param({}, id="empty"),
    ],
)
async def test_a_malformed_notes_update_is_422(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage, body: dict[str, Any]
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("badnotes"))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{ADMIN}/{lead.id}", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    row = await _row(db_session, lead.id)
    assert (row.status, row.admin_notes, row.quoted_amount_cents) == ("new", None, None)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


async def test_the_detail_shows_admin_fields_and_only_unexpired_attachments(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    now = datetime.now(UTC)
    live = await seed_lead(
        db_engine,
        private,
        email=unique_email("detail"),
        images=[("one.png", PNG), ("two.png", PNG)],
    )
    expired = await seed_lead(
        db_engine,
        private,
        email=unique_email("expired"),
        submitted_at=now - timedelta(days=91),
        expires_at=now - timedelta(seconds=1),
        images=[("old.png", PNG)],
    )
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        body = client.get(f"{ADMIN}/{live.id}").json()
        assert client.get(f"{ADMIN}/{expired.id}").json()["attachments"] == []
    assert body["description"] == live.description and body["phone"] == live.phone
    assert body["admin_notes"] is None and body["status"] == "new"
    assert sorted(a["original_filename"] for a in body["attachments"]) == ["one.png", "two.png"]
    assert set(body["attachments"][0]) == {
        "id",
        "original_filename",
        "mime_type",
        "size_bytes",
        "expires_at",
        "created_at",
    }
    assert "storage_key" not in str(body) and "custom-requests/" not in str(body)
    [audit] = await _audits(db_session, live.id, "custom_request.viewed")
    assert audit.actor_user_id == admin_id


async def test_the_list_is_in_pipeline_order_across_pages_and_audited(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    email = unique_email("queue")
    base = datetime(2026, 3, 1, tzinfo=UTC)
    plan = [("lost", 0), ("new", 3), ("quoted", 1), ("new", 2), ("closed", 4), ("contacted", 2)]
    seeded = [
        await seed_lead(
            db_engine,
            private,
            email=email,
            submitted_at=base + timedelta(hours=h),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            status=state,
            images=[("a.png", PNG)] if state == "new" else [],
        )
        for state, h in plan
    ]
    order = ["new", "contacted", "quoted", "in_progress", "completed", "closed", "lost"]
    states = dict(zip((s.id for s in seeded), (state for state, _ in plan), strict=True))
    expected = [
        str(s.id)
        for s in sorted(seeded, key=lambda s: (order.index(states[s.id]), s.created_at, s.id))
    ]
    seen: list[dict[str, Any]] = []
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"email": email.upper(), "limit": 4}
            if cursor:
                params["cursor"] = cursor
            page = client.get(ADMIN, params=params).json()
            seen += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
    assert [item["id"] for item in seen] == expected
    assert [item["attachment_count"] for item in seen[:2]] == [1, 1]
    assert "description" not in seen[0] and "admin_notes" not in seen[0]
    mine = [
        a
        for a in await _audits(db_session, None, "custom_request.list_viewed")
        if a.actor_user_id == admin_id
    ]
    assert [a.after_data["result_count"] for a in mine] == [4, 2]
    assert all(email not in str(a.after_data) for a in mine)


async def test_the_list_filters_by_status_and_date(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    email = unique_email("filter")
    base = datetime(2026, 4, 1, tzinfo=UTC)
    early = await seed_lead(db_engine, private, email=email, submitted_at=base)
    late = await seed_lead(db_engine, private, email=email, submitted_at=base + timedelta(days=2))
    quoted = await seed_lead(db_engine, private, email=email, submitted_at=base, status="quoted")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)

        def ids(**params: Any) -> list[str]:
            response = client.get(ADMIN, params={"email": email, **params})
            assert response.status_code == 200, response.text
            return [item["id"] for item in response.json()["items"]]

        assert ids(status="new") == [str(early.id), str(late.id)]
        assert ids(status="quoted") == [str(quoted.id)]
        after = (base + timedelta(days=1)).isoformat()
        assert ids(created_after=after) == [str(late.id)]
        assert ids(created_before=after) == [str(early.id), str(quoted.id)]
        bad = [
            {"cursor": "not-a-cursor"},
            {"status": "spam"},
            {"created_after": "2026-04-01T00:00:00"},
            {"created_after": after, "created_before": after},
            {"limit": 101},
        ]
        for params in bad:
            assert_problem(client.get(ADMIN, params=params), 422, "VALIDATION_ERROR")
