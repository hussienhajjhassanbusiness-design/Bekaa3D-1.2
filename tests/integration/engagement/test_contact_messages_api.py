"""VS-033 / FR-16: the public contact form and the admin message queue."""

import io
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.api import contact_messages as contact_module
from app.engagement.infrastructure.models import ContactMessageModel
from app.integrations.captcha.factory import get_captcha_verifier
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS, FakeCaptcha
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    fresh_ip,
    login,
    mfa_admin,
    unique_email,
)

CONTACT = "/api/v1/contact-messages"
ADMIN = "/api/v1/admin/contact-messages"


@pytest.fixture
def captcha() -> Iterator[FakeCaptcha]:
    fake = FakeCaptcha()
    main_app.dependency_overrides[get_captcha_verifier] = lambda: fake
    yield fake
    main_app.dependency_overrides.pop(get_captcha_verifier, None)


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """See test_deep_logs_and_leaks.py: capture through the app's own formatter."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    return buffer


def _form(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Rima Haddad",
        "email": unique_email("contact"),
        "phone": "+961 3 123 456",
        "subject": "Bulk keychains",
        "message": "Hello,\nCan you print 40 keychains?",
        "captcha_token": FAKE_CAPTCHA_PASS,
    }
    return body | overrides


async def _count(db: AsyncSession, email: str) -> int:
    db.expire_all()
    return int(
        await db.scalar(
            select(func.count())
            .select_from(ContactMessageModel)
            .where(ContactMessageModel.email == email)
        )
        or 0
    )


async def _seed(db: AsyncSession, **values: Any) -> ContactMessageModel:
    defaults = {"name": "Seeded", "email": unique_email("seed"), "message": "seeded message"}
    row = ContactMessageModel(**(defaults | values))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# --------------------------------------------------------------------------
# Public form
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_valid_message_enters_the_queue_as_new(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    body = _form(name="  Rima  ", subject="  ", phone="")
    with client_for(main_app) as client:
        response = client.post(CONTACT, json=body)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "created_at"}
    row = await db_session.get(ContactMessageModel, uuid.UUID(response.json()["id"]))
    assert row is not None
    assert (row.name, row.subject, row.phone, row.status) == ("Rima", None, None, "new")
    assert row.message == body["message"]
    assert captcha.calls == [FAKE_CAPTCHA_PASS]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("token", "available", "status", "code"),
    [
        pytest.param(None, True, 422, "VALIDATION_ERROR", id="missing"),
        pytest.param("", True, 400, "CAPTCHA_INVALID", id="empty"),
        pytest.param("forged-token", True, 400, "CAPTCHA_INVALID", id="refused"),
        pytest.param(FAKE_CAPTCHA_PASS, False, 503, "SERVICE_UNAVAILABLE", id="unavailable"),
    ],
)
async def test_a_bad_captcha_stores_nothing(
    db_session: AsyncSession,
    captcha: FakeCaptcha,
    token: str | None,
    available: bool,
    status: int,
    code: str,
) -> None:
    captcha.available = available
    body = _form(captcha_token=token)
    if token is None:
        del body["captcha_token"]
    with client_for(main_app) as client:
        response = client.post(CONTACT, json=body)
    assert_problem(response, status, code)
    if status == 503:
        assert response.headers["retry-after"] == "30"
    assert await _count(db_session, body["email"]) == 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_refused_captcha_spends_no_per_ip_or_per_email_quota(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    email = unique_email("quota")
    with client_for(main_app) as client:
        for _ in range(10):
            refused = client.post(CONTACT, json=_form(email=email, captcha_token="bad"))
            assert_problem(refused, 400, "CAPTCHA_INVALID")
        accepted = [client.post(CONTACT, json=_form(email=email)) for _ in range(5)]
    assert [r.status_code for r in accepted] == [201] * 5
    assert await _count(db_session, email) == 5


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_sixth_message_from_one_ip_is_rate_limited(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    with client_for(main_app) as client:
        responses = [client.post(CONTACT, json=_form()) for _ in range(6)]
    assert [r.status_code for r in responses[:5]] == [201] * 5
    assert_problem(responses[5], 429, "RATE_LIMITED")
    assert "retry-after" in responses[5].headers


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_sixth_message_from_one_email_is_rate_limited_across_ips(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    email = unique_email("same")
    responses = []
    for index in range(6):
        sender = email.upper() if index % 2 else email
        with client_for(main_app, ip=fresh_ip()) as client:
            responses.append(client.post(CONTACT, json=_form(email=sender)))
    assert [r.status_code for r in responses[:5]] == [201] * 5
    assert_problem(responses[5], 429, "RATE_LIMITED")
    assert await _count(db_session, email) == 5


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_61st_attempt_is_refused_before_the_verifier_is_called(
    captcha: FakeCaptcha,
) -> None:
    with client_for(main_app) as client:
        for _ in range(contact_module.ATTEMPT_LIMIT):
            assert client.post(CONTACT, json=_form(captcha_token="bad")).status_code == 400
        assert len(captcha.calls) == contact_module.ATTEMPT_LIMIT
        over_bad = client.post(CONTACT, json=_form(captcha_token="bad"))
        over_good = client.post(CONTACT, json=_form())
    assert_problem(over_bad, 429, "RATE_LIMITED")
    assert_problem(over_good, 429, "RATE_LIMITED")
    assert len(captcha.calls) == contact_module.ATTEMPT_LIMIT


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"name": "   "}, id="blank-name"),
        pytest.param({"name": "n" * 101}, id="long-name"),
        pytest.param({"email": "not-an-email"}, id="bad-email"),
        pytest.param({"phone": "call me maybe"}, id="bad-phone"),
        pytest.param({"subject": "s" * 201}, id="long-subject"),
        pytest.param({"message": " \n "}, id="blank-message"),
        pytest.param({"message": "m" * 5001}, id="long-message"),
        pytest.param({"message": "nul\x00byte"}, id="control-character"),
        pytest.param({"captcha_token": "t" * 2049}, id="long-token"),
        pytest.param({"status": "replied"}, id="unknown-field"),
    ],
)
async def test_invalid_fields_are_refused_before_the_captcha_and_store_nothing(
    db_session: AsyncSession, captcha: FakeCaptcha, overrides: dict[str, Any]
) -> None:
    body = _form(**overrides)
    with client_for(main_app) as client:
        response = client.post(CONTACT, json=body)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert captcha.calls == []
    if "@" in body["email"]:
        assert await _count(db_session, body["email"]) == 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_repeated_submissions_are_separate_messages(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    body = _form()
    with client_for(main_app) as client:
        first = client.post(CONTACT, json=body)
        second = client.post(CONTACT, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert await _count(db_session, body["email"]) == 2


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_form_ignores_auth_cookies_and_needs_no_csrf(
    db_session: AsyncSession, captcha: FakeCaptcha
) -> None:
    customer = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, customer.email)
        response = client.post(CONTACT, json=_form())
    assert response.status_code == 201, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_message_body_and_sender_never_reach_the_logs(
    db_session: AsyncSession, captcha: FakeCaptcha, app_logs: io.StringIO
) -> None:
    sentinel = f"body-sentinel-{uuid.uuid4().hex}"
    body = _form(message=sentinel, name=f"name-{sentinel}")
    with client_for(main_app) as client:
        created = client.post(CONTACT, json=body)
        assert created.status_code == 201
        assert client.post(CONTACT, json=body | {"phone": "bad"}).status_code == 422
        captcha.available = False
        assert client.post(CONTACT, json=body).status_code == 503
        client.cookies.clear()
        await mfa_admin(client, db_session)
        message_id = created.json()["id"]
        assert client.get(f"{ADMIN}/{message_id}").status_code == 200
        patched = client.patch(
            f"{ADMIN}/{message_id}", json={"status": "read"}, headers=csrf(client)
        )
        assert patched.status_code == 200
    logs = app_logs.getvalue()
    assert "contact_message_received" in logs, "log capture is not working"
    assert sentinel not in logs
    assert body["email"] not in logs
    db_session.expire_all()
    audits = (await db_session.scalars(select(AuditLogModel))).all()
    dumped = " ".join(f"{a.before_data} {a.after_data}" for a in audits)
    assert sentinel not in dumped
    assert body["email"] not in dumped


# --------------------------------------------------------------------------
# Admin queue
# --------------------------------------------------------------------------

ADMIN_ROUTES = [
    pytest.param("GET", ADMIN, id="list"),
    pytest.param("GET", f"{ADMIN}/{uuid.uuid4()}", id="detail"),
    pytest.param("PATCH", f"{ADMIN}/{uuid.uuid4()}", id="update"),
]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
async def test_visitors_customers_and_unfinished_admins_cannot_reach_the_queue(
    db_session: AsyncSession, method: str, path: str
) -> None:
    customer = await create_user(db_session)
    no_mfa = await create_user(db_session, role="admin")  # type: ignore[arg-type]
    with client_for(main_app) as client:
        assert_problem(client.request(method, path, json={"status": "read"}), 401)
        login(client, customer.email)
        response = client.request(method, path, json={"status": "read"}, headers=csrf(client))
        assert_problem(response, 404, "NOT_FOUND")
        client.cookies.clear()
        login(client, no_mfa.email)
        response = client.request(method, path, json={"status": "read"}, headers=csrf(client))
        assert_problem(response, 401, "MFA_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_status_change_requires_csrf(db_session: AsyncSession) -> None:
    row = await _seed(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{ADMIN}/{row.id}", json={"status": "read"})
    assert_problem(response, 403, "CSRF_INVALID")
    await db_session.refresh(row)
    assert row.status == "new"


async def _audits(db: AsyncSession, entity_id: uuid.UUID | None, action: str) -> list[Any]:
    stmt = select(AuditLogModel).where(AuditLogModel.action == action)
    if entity_id is not None:
        stmt = stmt.where(AuditLogModel.entity_id == entity_id)
    return list((await db.scalars(stmt.order_by(AuditLogModel.created_at))).all())


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_status_change_is_written_and_audited(db_session: AsyncSession) -> None:
    row = await _seed(db_session)
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        response = client.patch(
            f"{ADMIN}/{row.id}", json={"status": "replied"}, headers=csrf(client)
        )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "replied"
    await db_session.refresh(row)
    assert row.status == "replied"
    assert row.updated_at > row.created_at
    [audit] = await _audits(db_session, row.id, "contact_message.status_changed")
    assert (audit.actor_user_id, audit.entity_type) == (admin_id, "contact_message")
    assert (audit.before_data, audit.after_data) == ({"status": "new"}, {"status": "replied"})


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_setting_the_same_status_is_a_no_op_but_still_audited(
    db_session: AsyncSession,
) -> None:
    row = await _seed(db_session, status="read")
    updated_at = row.updated_at
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{ADMIN}/{row.id}", json={"status": "read"}, headers=csrf(client))
    assert response.status_code == 200
    await db_session.refresh(row)
    assert row.updated_at == updated_at
    [audit] = await _audits(db_session, row.id, "contact_message.status_changed")
    assert audit.before_data == audit.after_data == {"status": "read"}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("current", "target"),
    [("read", "new"), ("replied", "read"), ("archived", "new"), ("archived", "replied")],
)
async def test_moving_backwards_is_409_and_writes_nothing(
    db_session: AsyncSession, current: str, target: str
) -> None:
    row = await _seed(db_session, status=current)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{ADMIN}/{row.id}", json={"status": target}, headers=csrf(client))
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    await db_session.refresh(row)
    assert row.status == current
    assert await _audits(db_session, row.id, "contact_message.status_changed") == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "body",
    [{"status": "spam"}, {}, {"status": "read", "message": "edited"}],
    ids=["unknown-status", "empty", "extra-field"],
)
async def test_a_malformed_update_is_422(db_session: AsyncSession, body: dict[str, Any]) -> None:
    row = await _seed(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{ADMIN}/{row.id}", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_an_unknown_message_is_404_and_unaudited(
    db_session: AsyncSession, method: str
) -> None:
    missing = uuid.uuid4()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.request(
            method, f"{ADMIN}/{missing}", json={"status": "read"}, headers=csrf(client)
        )
    assert_problem(response, 404, "NOT_FOUND")
    db_session.expire_all()
    assert (
        await db_session.scalar(select(AuditLogModel).where(AuditLogModel.entity_id == missing))
        is None
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reading_a_message_is_audited_and_does_not_mark_it_read(
    db_session: AsyncSession,
) -> None:
    row = await _seed(db_session, phone="01 234 567", subject="Hi")
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        response = client.get(f"{ADMIN}/{row.id}")
    assert response.status_code == 200
    assert response.json() | {"created_at": None, "updated_at": None} == {
        "id": str(row.id),
        "name": "Seeded",
        "email": row.email,
        "phone": "01 234 567",
        "subject": "Hi",
        "message": "seeded message",
        "status": "new",
        "created_at": None,
        "updated_at": None,
        "user_id": None,  # a contact-form message; VS-029b's problem reports set both
        "order_id": None,
    }
    [audit] = await _audits(db_session, row.id, "contact_message.viewed")
    assert audit.actor_user_id == admin_id
    await db_session.refresh(row)
    assert row.status == "new"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_queue_lists_new_first_then_oldest_first_across_pages(
    db_session: AsyncSession,
) -> None:
    email = unique_email("queue")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    plan = [("read", 0), ("new", 3), ("archived", 1), ("new", 2), ("replied", 4), ("new", 2)]
    seeded = [
        await _seed(db_session, email=email, status=state, created_at=base + timedelta(hours=h))
        for state, h in plan
    ]
    order = {"new": 0, "read": 1, "replied": 2, "archived": 3}
    expected = [
        str(r.id) for r in sorted(seeded, key=lambda r: (order[r.status], r.created_at, r.id))
    ]
    seen: list[str] = []
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"email": email.upper(), "limit": 4}
            if cursor:
                params["cursor"] = cursor
            page = client.get(ADMIN, params=params).json()
            seen += [item["id"] for item in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
    assert seen == expected
    audits = await _audits(db_session, None, "contact_message.list_viewed")
    mine = [a for a in audits if a.actor_user_id == admin_id]
    assert [a.after_data["result_count"] for a in mine] == [4, 2]
    assert all(email not in str(a.after_data) for a in mine)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_queue_filters_by_status_and_date(db_session: AsyncSession) -> None:
    email = unique_email("filter")
    base = datetime(2026, 2, 1, tzinfo=UTC)
    early = await _seed(db_session, email=email, status="new", created_at=base)
    late = await _seed(db_session, email=email, status="new", created_at=base + timedelta(days=2))
    await _seed(db_session, email=email, status="archived", created_at=base)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)

        def ids(**params: Any) -> list[str]:
            response = client.get(ADMIN, params={"email": email, **params})
            assert response.status_code == 200, response.text
            return [item["id"] for item in response.json()["items"]]

        assert ids(status="new") == [str(early.id), str(late.id)]
        assert ids(status="new", created_after=(base + timedelta(days=1)).isoformat()) == [
            str(late.id)
        ]
        assert ids(status="new", created_before=(base + timedelta(days=2)).isoformat()) == [
            str(early.id)
        ]
        assert len(ids()) == 3


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-a-cursor"},
        {"cursor": "bmV3fDIwMjYtMDEtMDFUMDA6MDA6MDB8bm90LWEtdXVpZA"},
        {"status": "spam"},
        {"created_after": "2026-01-01T00:00:00"},
        {"created_after": "2026-01-02T00:00Z", "created_before": "2026-01-01T00:00Z"},
        {"limit": 0},
        {"limit": 101},
    ],
)
async def test_bad_query_parameters_are_422(
    db_session: AsyncSession, params: dict[str, Any]
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(ADMIN, params=params)
    assert_problem(response, 422, "VALIDATION_ERROR")
