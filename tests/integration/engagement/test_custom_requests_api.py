"""VS-034 / FR-15: the public Bring Your Idea form - captcha, limits, the ADR-021 image
pipeline into private storage, the admin notifications and what is never stored."""

import hashlib
import io
import logging
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.engagement.api import custom_requests as module
from app.engagement.domain.custom_request import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS
from app.engagement.infrastructure.models import (
    CustomRequestAttachmentModel,
    CustomRequestModel,
    NotificationModel,
)
from app.identity.domain.enums import UserRole
from app.identity.public import active_administrator_ids
from app.integrations.captcha.factory import get_captcha_verifier
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS, FakeCaptcha
from app.integrations.scanning.factory import get_malware_scanner
from app.integrations.scanning.fake import EICAR, FakeScanner
from app.integrations.storage.factory import get_private_upload_storage, get_public_media_storage
from app.integrations.storage.local import LocalStorage
from app.main import app as main_app
from app.platform.public import settings_reader
from tests.image_samples import SECRET, sample
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    fresh_ip,
    login,
    unique_email,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

URL = "/api/v1/custom-requests"
EVENT = "custom_request.submitted"


class Uploads:
    def __init__(self, root: Path) -> None:
        self.private_root = root / "private"
        self.public_root = root / "public"
        self.private = LocalStorage(self.private_root)
        self.public = LocalStorage(self.public_root)
        self.scanner = FakeScanner()
        self.captcha = FakeCaptcha()

    def private_files(self) -> list[Path]:
        return sorted(p for p in self.private_root.rglob("*") if p.is_file())

    def public_files(self) -> list[Path]:
        return sorted(p for p in self.public_root.rglob("*") if p.is_file())


@pytest.fixture
def uploads(tmp_path: Path) -> Iterator[Uploads]:
    state = Uploads(tmp_path)
    overrides: dict[Any, Any] = {
        get_private_upload_storage: lambda: state.private,
        get_public_media_storage: lambda: state.public,
        get_malware_scanner: lambda: state.scanner,
        get_captcha_verifier: lambda: state.captcha,
    }
    main_app.dependency_overrides.update(overrides)
    yield state
    for dependency in overrides:
        main_app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """See test_deep_logs_and_leaks.py: capture through the app's own formatter."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    return buffer


def _form(**overrides: Any) -> dict[str, Any]:
    form: dict[str, Any] = {
        "name": "Rima Haddad",
        "email": unique_email("byi"),
        "phone": "+961 3 123 456",
        "project_title": "Cedar lamp",
        "description": "A lamp shaped like a cedar.\nAbout 30 cm tall.",
        "preferred_material": "PLA",
        "preferred_colour": "Green",
        "dimensions": "30 x 20 x 20 cm",
        "captcha_token": FAKE_CAPTCHA_PASS,
    }
    return {k: v for k, v in (form | overrides).items() if v is not None}


def _files(*blobs: bytes, name: str = "photo.jpg", kind: str = "image/jpeg") -> list[Any]:
    return [("attachments", (f"{i}-{name}", blob, kind)) for i, blob in enumerate(blobs)]


def _submit(client: TestClient, form: dict[str, Any], *blobs: bytes, **kw: Any) -> Any:
    return client.post(URL, data=form, files=_files(*blobs, **kw) or None)


async def _requests_for(db: AsyncSession, email: str) -> list[CustomRequestModel]:
    db.expire_all()
    stmt = select(CustomRequestModel).where(CustomRequestModel.email == email)
    return list((await db.scalars(stmt)).all())


async def _attachments(db: AsyncSession, request_id: str) -> list[CustomRequestAttachmentModel]:
    db.expire_all()
    stmt = (
        select(CustomRequestAttachmentModel)
        .where(CustomRequestAttachmentModel.custom_request_id == uuid.UUID(request_id))
        .order_by(CustomRequestAttachmentModel.original_filename)
    )
    return list((await db.scalars(stmt)).all())


async def _notifications(db: AsyncSession, request_id: str | None = None) -> list[Any]:
    db.expire_all()
    stmt = select(NotificationModel).where(NotificationModel.payload["event"].astext == EVENT)
    if request_id is not None:
        stmt = stmt.where(NotificationModel.payload["custom_request_id"].astext == request_id)
    return list((await db.scalars(stmt)).all())


async def _row_counts(db: AsyncSession) -> dict[str, int]:
    tables = await db.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    )
    return {t: int(await db.scalar(text(f'SELECT count(*) FROM "{t}"')) or 0) for t in tables.all()}


# --- a valid submission -----------------------------------------------------


async def test_a_valid_request_is_stored_with_private_reencoded_attachments(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    form = _form(name="  Rima  ", dimensions="  ")
    blobs = [sample("JPEG"), sample("PNG"), sample("WEBP")]
    with client_for(main_app) as client:
        response = client.post(
            URL,
            data=form,
            files=[
                ("attachments", ("a.jpg", blobs[0], "image/jpeg")),
                ("attachments", ("../../b.png", blobs[1], "image/png")),
                ("attachments", ("c.webp", blobs[2], "image/webp")),
            ],
        )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "created_at"}

    [row] = await _requests_for(db_session, form["email"])
    assert (row.name, row.dimensions, row.status, row.phone) == (
        "Rima",
        None,
        "new",
        "+961 3 123 456",
    )
    assert row.quoted_amount_cents is None and row.outcome is None
    rows = await _attachments(db_session, response.json()["id"])
    assert [a.original_filename for a in rows] == ["a.jpg", "b.png", "c.webp"]
    assert [a.mime_type for a in rows] == ["image/jpeg", "image/png", "image/webp"]
    retention = await settings_reader(db_session).get_duration_seconds(module.RETENTION_KEY)
    for attachment in rows:
        stored = (uploads.private_root / attachment.storage_key).read_bytes()
        assert attachment.storage_key.startswith("custom-requests/")
        assert attachment.checksum == hashlib.sha256(stored).hexdigest()
        assert attachment.size_bytes == len(stored)
        assert stored not in blobs and SECRET.encode() not in stored
        assert attachment.scan_status == "clean"
        assert attachment.expires_at - attachment.created_at == timedelta(seconds=retention)
    assert len(uploads.private_files()) == 3
    assert uploads.public_files() == []
    assert uploads.scanner.scanned == blobs


async def test_a_request_without_images_is_a_lead_too(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    form = _form()
    with client_for(main_app) as client:
        response = _submit(client, form)
    assert response.status_code == 201, response.text
    assert await _attachments(db_session, response.json()["id"]) == []
    assert uploads.private_files() == []


async def test_repeated_submissions_are_separate_requests(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    form = _form()
    with client_for(main_app) as client:
        ids = {_submit(client, form, sample("JPEG")).json()["id"] for _ in range(2)}
    assert len(ids) == 2
    assert len(await _requests_for(db_session, form["email"])) == 2


async def test_the_form_ignores_auth_cookies_and_needs_no_csrf(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    customer = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, customer.email)
        response = _submit(client, _form())
    assert response.status_code == 201, response.text


# --- BR-112: a lead, never a transaction; admin notifications --------------


async def test_a_submission_changes_only_the_lead_tables_and_notifications(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    before = await _row_counts(db_session)
    with client_for(main_app) as client:
        assert _submit(client, _form(), sample("JPEG")).status_code == 201
    after = await _row_counts(db_session)
    changed = {table for table in before if before[table] != after[table]}
    assert changed <= {"custom_requests", "custom_request_attachments", "notifications"}
    assert {"custom_requests", "custom_request_attachments"} <= changed


async def test_a_submission_notifies_every_active_admin_once_without_contact_details(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    disabled = (await create_user(db_session, role=UserRole.ADMIN, active=False)).id
    customer = (await create_user(db_session)).id
    admins = set(await active_administrator_ids(db_session))
    form = _form(project_title="Cedar lamp")
    with client_for(main_app) as client:
        request_id = _submit(client, form).json()["id"]

    sent = await _notifications(db_session, request_id)
    assert sorted(n.user_id for n in sent) == sorted(admins)
    assert disabled not in admins and customer not in admins
    for notification in sent:
        assert notification.type == "custom_request"
        assert notification.payload == {
            "event": EVENT,
            "custom_request_id": request_id,
            "project_title": "Cedar lamp",
            "title": "New Bring Your Idea request: Cedar lamp",
        }
        dumped = str(notification.payload)
        assert form["email"] not in dumped and form["phone"] not in dumped
        assert form["name"] not in dumped


@pytest.mark.parametrize("failure", ["captcha", "malware", "fake_type", "scanner_down"])
async def test_a_rejected_submission_notifies_nobody(
    db_session: AsyncSession, uploads: Uploads, failure: str
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    before = len(await _notifications(db_session))
    form = _form(captcha_token="bad") if failure == "captcha" else _form()
    blob = {"malware": sample("JPEG") + EICAR, "fake_type": b"%PDF-1.7"}.get(failure)
    uploads.scanner.available = failure != "scanner_down"
    with client_for(main_app) as client:
        response = _submit(client, form, blob or sample("JPEG"))
    assert response.status_code in {400, 422, 503}
    assert len(await _notifications(db_session)) == before


# --- captcha and rate limits ------------------------------------------------


@pytest.mark.parametrize(
    ("token", "available", "status", "code"),
    [
        pytest.param(None, True, 422, "VALIDATION_ERROR", id="missing"),
        # FastAPI reads an empty multipart value as absent (ADR-030); still never verified.
        pytest.param("", True, 422, "VALIDATION_ERROR", id="empty"),
        pytest.param("forged-token", True, 400, "CAPTCHA_INVALID", id="refused"),
        pytest.param(FAKE_CAPTCHA_PASS, False, 503, "SERVICE_UNAVAILABLE", id="unavailable"),
    ],
)
async def test_a_bad_captcha_stores_nothing(
    db_session: AsyncSession,
    uploads: Uploads,
    token: str | None,
    available: bool,
    status: int,
    code: str,
) -> None:
    uploads.captcha.available = available
    form = _form(captcha_token=token)
    with client_for(main_app) as client:
        response = _submit(client, form, sample("JPEG"))
    assert_problem(response, status, code)
    assert await _requests_for(db_session, form["email"]) == []
    assert uploads.private_files() == [] and uploads.scanner.scanned == []


async def test_a_refused_captcha_spends_no_per_ip_or_per_email_quota(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    email = unique_email("quota")
    with client_for(main_app) as client:
        for _ in range(8):
            refused = _submit(client, _form(email=email, captcha_token="bad"))
            assert_problem(refused, 400, "CAPTCHA_INVALID")
        accepted = [_submit(client, _form(email=email)) for _ in range(module.IP_LIMIT)]
    assert [r.status_code for r in accepted] == [201] * module.IP_LIMIT


async def test_the_sixth_request_from_one_ip_is_rate_limited(uploads: Uploads) -> None:
    with client_for(main_app) as client:
        responses = [_submit(client, _form(), sample("JPEG")) for _ in range(module.IP_LIMIT + 1)]
    assert [r.status_code for r in responses[:-1]] == [201] * module.IP_LIMIT
    assert_problem(responses[-1], 429, "RATE_LIMITED")
    assert "retry-after" in responses[-1].headers
    assert len(uploads.private_files()) == module.IP_LIMIT


async def test_the_sixth_request_from_one_email_is_rate_limited_across_ips(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    email = unique_email("same")
    responses = []
    for index in range(module.EMAIL_LIMIT + 1):
        with client_for(main_app, ip=fresh_ip()) as client:
            sender = email.upper() if index % 2 else email
            responses.append(_submit(client, _form(email=sender)))
    assert [r.status_code for r in responses[:-1]] == [201] * module.EMAIL_LIMIT
    assert_problem(responses[-1], 429, "RATE_LIMITED")
    assert len(await _requests_for(db_session, email)) == module.EMAIL_LIMIT


async def test_the_attempt_limit_refuses_before_the_body_is_parsed(
    uploads: Uploads, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(main_app) as client:
        for _ in range(module.ATTEMPT_LIMIT):
            assert _submit(client, _form(captcha_token="bad")).status_code == 400
        assert len(uploads.captcha.calls) == module.ATTEMPT_LIMIT

        async def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the body was parsed")

        monkeypatch.setattr(Request, "form", never)
        over = _submit(client, _form(), sample("JPEG"))
    assert_problem(over, 429, "RATE_LIMITED")
    assert len(uploads.captcha.calls) == module.ATTEMPT_LIMIT


# --- size, count, type and malware ------------------------------------------


async def test_an_oversized_or_unsized_body_is_refused_before_it_is_parsed(
    uploads: Uploads, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "MAX_BODY_BYTES", 4096)

    async def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the body was parsed")

    monkeypatch.setattr(Request, "form", never)
    with client_for(main_app) as client:
        oversized = _submit(client, _form(), bytes(5000))
        unsized = client.post(
            URL,
            content=iter([b"--x--"]),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
    assert_problem(oversized, 422, "UPLOAD_REJECTED")
    assert_problem(unsized, 422, "UPLOAD_REJECTED")
    assert uploads.captcha.calls == [] and uploads.private_files() == []


def test_the_body_cap_allows_five_full_size_images() -> None:
    assert module.MAX_BODY_BYTES == MAX_ATTACHMENTS * MAX_ATTACHMENT_BYTES + 64 * 1024


@pytest.mark.parametrize(
    "blobs",
    [
        pytest.param([bytes(MAX_ATTACHMENT_BYTES + 1)], id="oversized-file"),
        pytest.param([sample("JPEG")] * (MAX_ATTACHMENTS + 1), id="six-files"),
    ],
)
async def test_size_and_count_caps_are_checked_before_the_captcha(
    db_session: AsyncSession, uploads: Uploads, blobs: list[bytes]
) -> None:
    form = _form()
    with client_for(main_app) as client:
        response = _submit(client, form, *blobs)
    assert_problem(response, 422, "UPLOAD_REJECTED")
    assert uploads.captcha.calls == [] and uploads.scanner.scanned == []
    assert await _requests_for(db_session, form["email"]) == []


async def test_exactly_five_images_are_accepted(uploads: Uploads) -> None:
    with client_for(main_app) as client:
        response = _submit(client, _form(), *[sample("PNG")] * MAX_ATTACHMENTS)
    assert response.status_code == 201, response.text
    assert len(uploads.private_files()) == MAX_ATTACHMENTS


@pytest.mark.parametrize(
    "blob",
    [
        pytest.param(b"%PDF-1.7 pretending to be a photo", id="pdf"),
        pytest.param(b"<svg xmlns='http://www.w3.org/2000/svg'/>", id="svg"),
        pytest.param(b"GIF89a" + bytes(32), id="gif"),
    ],
)
async def test_a_fake_image_is_rejected_by_content_and_nothing_is_stored(
    db_session: AsyncSession, uploads: Uploads, blob: bytes
) -> None:
    form = _form()
    with client_for(main_app) as client:
        response = _submit(client, form, sample("JPEG"), blob, name="photo.jpg")
    assert_problem(response, 422, "UPLOAD_REJECTED")
    assert response.json()["errors"][0]["loc"] == ["body", "attachments", 1]
    assert await _requests_for(db_session, form["email"]) == []
    assert uploads.private_files() == []


@pytest.mark.parametrize(
    "blobs",
    [
        pytest.param([EICAR], id="eicar"),
        pytest.param([sample("JPEG"), sample("PNG"), sample("JPEG") + EICAR], id="third-file"),
    ],
)
async def test_malware_is_detected_and_none_of_the_files_is_stored(
    db_session: AsyncSession, uploads: Uploads, blobs: list[bytes]
) -> None:
    form = _form()
    with client_for(main_app) as client:
        response = _submit(client, form, *blobs)
    assert_problem(response, 422, "MALWARE_DETECTED")
    assert await _requests_for(db_session, form["email"]) == []
    assert uploads.private_files() == []


async def test_a_scanner_outage_is_503_and_nothing_is_stored(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    uploads.scanner.available = False
    form = _form()
    with client_for(main_app) as client:
        response = _submit(client, form, sample("JPEG"))
    assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    assert await _requests_for(db_session, form["email"]) == []
    assert uploads.private_files() == []


async def test_a_storage_failure_leaves_no_row_and_no_file(
    db_session: AsyncSession, uploads: Uploads, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_put = LocalStorage.put
    calls: list[str] = []

    async def failing_put(self: LocalStorage, key: str, data: bytes) -> None:
        calls.append(key)
        if len(calls) == 2:
            raise OSError("disk full")
        await real_put(self, key, data)

    monkeypatch.setattr(LocalStorage, "put", failing_put)
    form = _form()
    with client_for(main_app, raise_server_exceptions=False) as client:
        response = _submit(client, form, sample("JPEG"), sample("PNG"))
    assert response.status_code == 500
    assert len(calls) == 2
    assert await _requests_for(db_session, form["email"]) == []
    assert uploads.private_files() == []


# --- validation, privacy and logs --------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": None},
        {"name": "   "},
        {"email": "not-an-email"},
        {"phone": None},
        {"phone": "12345"},
        {"project_title": None},
        {"project_title": "x" * 201},
        {"description": None},
        {"description": "x" * 5001},
        {"preferred_material": "x" * 101},
        {"preferred_colour": "x" * 101},
        {"dimensions": "x" * 201},
        {"name": "bad\x00name"},
        {"description": "bad\x07bell"},
    ],
)
async def test_invalid_fields_are_refused_before_the_captcha_and_store_nothing(
    db_session: AsyncSession, uploads: Uploads, overrides: dict[str, Any]
) -> None:
    form = _form(**overrides)
    with client_for(main_app) as client:
        response = _submit(client, form, sample("JPEG"))
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert uploads.captcha.calls == [] and uploads.private_files() == []
    if "email" in form:
        assert await _requests_for(db_session, form["email"]) == []


async def test_no_route_serves_attachments(db_session: AsyncSession, uploads: Uploads) -> None:
    with client_for(main_app) as client:
        response = _submit(client, _form(), sample("JPEG"))
        [attachment] = await _attachments(db_session, response.json()["id"])
        key = attachment.storage_key
        probes = [
            client.get(URL),
            client.get(f"{URL}/{response.json()['id']}"),
            client.get(f"/media/{key}"),
            client.get(f"/{key}"),
            client.get(f"/api/v1/{key}"),
        ]
    assert all(p.status_code in {404, 405} for p in probes), [p.status_code for p in probes]
    paths = [p for p in main_app.openapi()["paths"] if p.startswith(URL)]
    assert paths == [URL] and set(main_app.openapi()["paths"][URL]) == {"post"}
    assert key not in response.text


async def test_the_submission_details_never_reach_the_logs(
    db_session: AsyncSession, uploads: Uploads, app_logs: io.StringIO
) -> None:
    sentinel = f"sentinel-{uuid.uuid4().hex}"
    form = _form(name=f"n-{sentinel}", description=f"d-{sentinel}", project_title=sentinel)
    with client_for(main_app) as client:
        assert _submit(client, form, sample("JPEG")).status_code == 201
        assert _submit(client, form, sample("JPEG") + EICAR).status_code == 422
        assert _submit(client, form | {"phone": "bad"}).status_code == 422
    logs = app_logs.getvalue()
    assert "custom_request_received" in logs, "log capture is not working"
    assert sentinel not in logs
    assert form["email"] not in logs and form["phone"] not in logs
    count = await db_session.scalar(
        select(func.count())
        .select_from(CustomRequestModel)
        .where(CustomRequestModel.email == form["email"])
    )
    assert count == 1


async def test_expiry_is_stamped_from_the_retention_setting_at_submission(
    db_session: AsyncSession, uploads: Uploads
) -> None:
    """A changed setting applies to new uploads only (ADR-030)."""
    with client_for(main_app) as client:
        before = _submit(client, _form(), sample("JPEG")).json()["id"]
        await db_session.execute(
            text("UPDATE settings SET value = '86400' WHERE key = :k"), {"k": module.RETENTION_KEY}
        )
        await db_session.commit()
        try:
            after = _submit(client, _form(), sample("JPEG")).json()["id"]
        finally:
            await db_session.execute(
                text("UPDATE settings SET value = '7776000' WHERE key = :k"),
                {"k": module.RETENTION_KEY},
            )
            await db_session.commit()
    lifetimes = []
    for request_id in (before, after):
        [row] = await _attachments(db_session, request_id)
        lifetimes.append(row.expires_at - row.created_at)
    assert lifetimes == [timedelta(days=90), timedelta(days=1)]
