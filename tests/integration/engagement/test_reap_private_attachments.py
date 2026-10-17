"""VS-034 / FR-15 "orphaned uploads are removed": the reaper covers private attachments too."""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.engagement.application.commands.submit_custom_request import (
    AttachmentUpload,
    SubmitCustomRequest,
)
from app.engagement.infrastructure.administrators import IdentityAdministratorDirectory
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.engagement.infrastructure.repositories import NotificationRepository
from app.integrations.images.pillow import PillowImageSanitizer
from app.integrations.scanning.fake import FakeScanner
from app.integrations.storage.local import LocalStorage
from app.jobs import reap_orphan_files as reaper
from app.jobs.reap_orphan_files import CUSTOM_REQUEST_ATTACHMENTS, GRACE_PERIOD, reap
from tests.image_samples import sample
from tests.integration.engagement.custom_request_support import DETAILS, seed_request

pytestmark = pytest.mark.integration

WRITTEN_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
LATER = WRITTEN_AT + GRACE_PERIOD * 30


class _CommitFailedError(Exception):
    pass


def _age(root: Path, *keys: str) -> None:
    stamp = WRITTEN_AT.timestamp()
    for key in keys:
        os.utime(root / key, (stamp, stamp))


async def _orphans_from_a_failed_commit(engine: AsyncEngine, storage: LocalStorage) -> list[str]:
    """The files are written, then the transaction holding their rows rolls back."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    written: list[str] = []
    with pytest.raises(_CommitFailedError):
        async with factory() as session, session.begin():
            request = await SubmitCustomRequest(
                SqlCustomRequestRepository(session),
                NotificationRepository(session),
                IdentityAdministratorDirectory(session),
                storage=storage,
                scanner=FakeScanner(),
                sanitizer=PillowImageSanitizer(),
            ).execute(
                DETAILS,
                [
                    AttachmentUpload("a.jpg", sample("JPEG")),
                    AttachmentUpload("b.png", sample("PNG")),
                ],
                retention_seconds=86_400,
            )
            written += [a.storage_key for a in request.attachments]
            raise _CommitFailedError
    return written


async def test_orphans_from_a_failed_commit_are_reaped_and_referenced_files_kept(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    orphans = await _orphans_from_a_failed_commit(db_engine, storage)
    _, kept = await seed_request(db_engine, storage, expires_at=LATER + GRACE_PERIOD)
    _age(tmp_path, *orphans, *kept)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    removed = await reap(storage, factory, LATER, CUSTOM_REQUEST_ATTACHMENTS)

    assert sorted(removed) == sorted(orphans)
    assert [await storage.exists(k) for k in kept] == [True] * len(kept)


async def test_a_fresh_orphan_is_kept_inside_the_grace_period(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    orphans = await _orphans_from_a_failed_commit(db_engine, storage)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    assert await reap(storage, factory, datetime.now(UTC), CUSTOM_REQUEST_ATTACHMENTS) == []
    assert [await storage.exists(k) for k in orphans] == [True] * len(orphans)


async def test_the_daily_job_reaps_both_public_media_and_private_attachments(
    db_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public, private = LocalStorage(tmp_path / "public"), LocalStorage(tmp_path / "private")
    product_orphan = f"products/{uuid.uuid4()}.jpg"
    attachment_orphan = f"custom-requests/{uuid.uuid4()}.png"
    await public.put(product_orphan, b"x")
    await private.put(attachment_orphan, b"x")
    await private.put("other/keep.txt", b"not ours")
    _age(tmp_path / "public", product_orphan)
    _age(tmp_path / "private", attachment_orphan, "other/keep.txt")
    monkeypatch.setattr(reaper, "public_media_storage", lambda _settings: public)
    monkeypatch.setattr(reaper, "private_upload_storage", lambda _settings: private)

    ctx: dict[str, Any] = {"session_factory": async_sessionmaker(db_engine)}
    count = await reaper.reap_orphan_files(ctx)

    assert count == 2
    assert not await public.exists(product_orphan)
    assert not await private.exists(attachment_orphan)
    assert await private.exists("other/keep.txt")
