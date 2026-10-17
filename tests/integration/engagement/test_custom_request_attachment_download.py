"""VS-035 / BR-111, BR-115, ADR-031: the admin-only download of a private reference image."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.application.commands.purge_expired_attachments import PurgeExpiredAttachments
from app.engagement.domain.custom_request import CustomRequest
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.integrations.storage.factory import get_private_upload_storage
from app.integrations.storage.local import CHUNK_BYTES, LocalStorage
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import assert_problem, client_for, mfa_admin, unique_email
from tests.integration.engagement.custom_request_support import seed_lead

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ADMIN = "/api/v1/admin/custom-requests"
# Over one chunk, so the body really arrives in pieces.
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * (CHUNK_BYTES // 256 + 7)


@pytest.fixture
def private(tmp_path: Path) -> Iterator[LocalStorage]:
    storage = LocalStorage(tmp_path / "private")
    main_app.dependency_overrides[get_private_upload_storage] = lambda: storage
    yield storage
    main_app.dependency_overrides.pop(get_private_upload_storage, None)


def _url(lead: CustomRequest, index: int = 0, *, request_id: uuid.UUID | None = None) -> str:
    attachment = lead.attachments[index]
    return f"{ADMIN}/{request_id or lead.id}/attachments/{attachment.id}/download"


async def _downloads(db: AsyncSession, attachment_id: uuid.UUID) -> list[Any]:
    db.expire_all()
    stmt = select(AuditLogModel).where(
        AuditLogModel.action == "custom_request_attachment.downloaded",
        AuditLogModel.entity_id == attachment_id,
    )
    return list((await db.scalars(stmt)).all())


async def test_the_download_streams_the_exact_bytes_as_an_inert_attachment(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    lead = await seed_lead(
        db_engine, private, email=unique_email("dl"), images=[('ev"il صورة.html', PNG)]
    )
    with client_for(main_app) as client:
        admin_id = (await mfa_admin(client, db_session))[0].id
        response = client.get(_url(lead), headers={"Range": "bytes=0-9"})
    assert response.status_code == 200, response.text
    assert response.content == PNG
    headers = response.headers
    assert headers["content-type"] == "image/png"
    assert headers["content-length"] == str(len(PNG))
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert headers["cross-origin-resource-policy"] == "same-origin"
    assert "content-range" not in headers and "accept-ranges" not in headers
    disposition = headers["content-disposition"]
    assert disposition.startswith('attachment; filename="ev_il ____.png"; ')
    assert unquote(disposition.split("filename*=UTF-8''", 1)[1]) == 'ev"il صورة.png'
    [audit] = await _downloads(db_session, lead.attachments[0].id)
    assert (audit.actor_user_id, audit.entity_type) == (admin_id, "custom_request_attachment")
    assert audit.after_data == {"custom_request_id": str(lead.id)}


@pytest.mark.parametrize(
    ("offset", "served"),
    [(timedelta(seconds=-1), True), (timedelta(0), False), (timedelta(seconds=1), False)],
    ids=["expiry-minus-1s", "exactly-at-expiry", "expiry-plus-1s"],
)
async def test_an_expired_attachment_cannot_be_downloaded(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    private: LocalStorage,
    offset: timedelta,
    served: bool,
) -> None:
    """Done-when (VS-035): expiry is the purge job's `expires_at <= now`, not the purge run."""
    expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=2)
    lead = await seed_lead(
        db_engine,
        private,
        email=unique_email("exp"),
        expires_at=expires_at,
        images=[("a.png", PNG)],
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        with time_machine.travel(expires_at + offset, tick=False):
            response = client.get(_url(lead))
            detail = client.get(f"{ADMIN}/{lead.id}").json()
    if served:
        assert response.status_code == 200 and response.content == PNG
    else:
        assert_problem(response, 404, "NOT_FOUND")
        assert PNG not in response.content
    assert len(detail["attachments"]) == (1 if served else 0)
    assert len(await _downloads(db_session, lead.attachments[0].id)) == (1 if served else 0)


async def test_an_attachment_asked_for_under_another_request_is_404(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    mine = await seed_lead(db_engine, private, email=unique_email("a"), images=[("a.png", PNG)])
    other = await seed_lead(db_engine, private, email=unique_email("b"), images=[("b.png", PNG)])
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        probes = [
            client.get(_url(mine, request_id=other.id)),
            client.get(_url(mine, request_id=uuid.uuid4())),
            client.get(f"{ADMIN}/{mine.id}/attachments/{uuid.uuid4()}/download"),
            client.get(f"{ADMIN}/{mine.id}/attachments/not-a-uuid/download"),
        ]
    for response in probes[:3]:
        assert_problem(response, 404, "NOT_FOUND")
    assert_problem(probes[3], 422, "VALIDATION_ERROR")
    assert all(PNG not in p.content for p in probes)
    assert await _downloads(db_session, mine.attachments[0].id) == []


async def test_a_purged_attachment_is_404(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    now = datetime.now(UTC)
    lead = await seed_lead(
        db_engine,
        private,
        email=unique_email("purged"),
        submitted_at=now - timedelta(days=90),
        expires_at=now - timedelta(seconds=1),
        images=[("a.png", PNG)],
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        purge = PurgeExpiredAttachments(SqlCustomRequestRepository(session), private)
        assert await purge.execute_batch(now=now, limit=10_000) >= 1
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert_problem(client.get(_url(lead)), 404, "NOT_FOUND")


async def test_a_row_whose_file_is_gone_is_404_and_unaudited(
    db_session: AsyncSession, db_engine: AsyncEngine, private: LocalStorage
) -> None:
    lead = await seed_lead(db_engine, private, email=unique_email("gone"), images=[("a.png", PNG)])
    await private.delete(lead.attachments[0].storage_key)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(_url(lead))
    assert_problem(response, 404, "NOT_FOUND")
    assert await _downloads(db_session, lead.attachments[0].id) == []


async def test_the_public_submission_route_still_serves_no_attachment(
    db_engine: AsyncEngine, private: LocalStorage
) -> None:
    """BR-111: only the admin route serves bytes; the public prefix has POST alone."""
    lead = await seed_lead(db_engine, private, email=unique_email("pub"), images=[("a.png", PNG)])
    public = f"/api/v1/custom-requests/{lead.id}/attachments/{lead.attachments[0].id}/download"
    with client_for(main_app) as client:
        response = client.get(public)
    assert response.status_code in {404, 405} and PNG not in response.content
    paths = main_app.openapi()["paths"]
    serving = [p for p in paths if "attachments" in p]
    assert serving == [f"{ADMIN}/{{request_id}}/attachments/{{attachment_id}}/download"]
