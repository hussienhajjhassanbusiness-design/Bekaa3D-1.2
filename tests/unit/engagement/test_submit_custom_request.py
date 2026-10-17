"""VS-034 / FR-15 failure behaviour: every file is screened before any is stored, the
request and its attachments land together, and stored files are removed on failure."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.engagement.application.commands.submit_custom_request import (
    AttachmentUpload,
    CustomRequestSubmission,
    SubmitCustomRequest,
)
from app.engagement.domain.custom_request import (
    MAX_ATTACHMENTS,
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    NewAttachment,
)
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import CustomRequestStatus, NotificationType
from app.engagement.domain.exceptions import AttachmentMalwareError, AttachmentRejectedError
from app.integrations.images.pillow import PillowImageSanitizer
from app.integrations.scanning.fake import EICAR, FakeScanner
from app.integrations.scanning.ports import ScannerUnavailableError
from app.integrations.storage.ports import StoragePort, StoredObject
from tests.image_samples import sample

DETAILS = CustomRequestDetails.of(
    name="Rima",
    email="rima@example.com",
    phone="+961 3 123 456",
    project_title="Cedar lamp",
    description="A lamp.",
)


class MemoryStorage(StoragePort):
    def __init__(self, *, fail_on_put: int | None = None) -> None:
        self.files: dict[str, bytes] = {}
        self.puts = 0
        self.fail_on_put = fail_on_put

    async def put(self, key: str, data: bytes) -> None:
        self.puts += 1
        if self.puts == self.fail_on_put:
            raise OSError("disk full")
        self.files[key] = data

    async def exists(self, key: str) -> bool:
        return key in self.files

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)

    async def list(self, prefix: str) -> list[StoredObject]:
        now = datetime.now(UTC)
        return [StoredObject(k, now) for k in self.files if k.startswith(prefix)]


class MemoryRequests:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.added: list[tuple[CustomRequestDetails, list[NewAttachment], datetime]] = []

    async def add(
        self,
        details: CustomRequestDetails,
        attachments: Sequence[NewAttachment],
        *,
        submitted_at: datetime,
        expires_at: datetime,
    ) -> CustomRequest:
        if self.fail:
            raise RuntimeError("insert failed")
        self.added.append((details, list(attachments), expires_at))
        request_id = uuid.uuid4()
        rows = tuple(
            CustomRequestAttachment(
                id=uuid.uuid4(),
                custom_request_id=request_id,
                expires_at=expires_at,
                created_at=submitted_at,
                **vars(a),
            )
            for a in attachments
        )
        return CustomRequest(
            id=request_id,
            project_title=details.project_title,
            status=CustomRequestStatus.NEW,
            created_at=submitted_at,
            attachments=rows,
        )

    async def lock_expired_attachments(
        self, *, now: datetime, limit: int
    ) -> list[CustomRequestAttachment]:
        return []

    async def delete_attachments(self, attachment_ids: Sequence[UUID]) -> int:
        return 0


class MemoryNotifications:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[UUID, NotificationType, dict[str, Any]]] = []

    async def add(
        self, *, user_id: UUID, notification_type: NotificationType, payload: dict[str, Any]
    ) -> Notification:
        if self.fail:
            raise RuntimeError("notification insert failed")
        self.sent.append((user_id, notification_type, payload))
        return Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type=notification_type,
            payload=payload,
            read_at=None,
            created_at=datetime.now(UTC),
        )


class Admins:
    def __init__(self, ids: list[UUID]) -> None:
        self.ids = ids

    async def active_administrator_ids(self) -> list[UUID]:
        return self.ids


class Harness:
    def __init__(self, **kw: Any) -> None:
        self.storage: MemoryStorage = kw.get("storage", MemoryStorage())
        self.scanner = FakeScanner(available=kw.get("scanner_up", True))
        self.requests = MemoryRequests(fail=kw.get("insert_fails", False))
        self.notifications = MemoryNotifications(fail=kw.get("notify_fails", False))
        self.admins = Admins(kw.get("admins", [uuid.uuid4(), uuid.uuid4()]))

    async def submit(self, *uploads: bytes) -> CustomRequestSubmission:
        command = SubmitCustomRequest(
            self.requests,
            self.notifications,
            self.admins,
            storage=self.storage,
            scanner=self.scanner,
            sanitizer=PillowImageSanitizer(),
        )
        files = [AttachmentUpload(f"photo{i}.jpg", data) for i, data in enumerate(uploads)]
        return await command.execute(DETAILS, files, retention_seconds=86_400)


def _jpeg() -> bytes:
    return sample("JPEG")


async def test_a_clean_submission_stores_every_file_and_notifies_each_admin() -> None:
    harness = Harness()
    submission = await harness.submit(_jpeg(), sample("PNG"))
    assert submission.failed_notifications == 0
    assert len(harness.storage.files) == 2
    [(_, attachments, _)] = harness.requests.added
    assert {a.storage_key for a in attachments} == set(harness.storage.files)
    assert [a.mime_type for a in attachments] == ["image/jpeg", "image/png"]
    assert [user for user, _, _ in harness.notifications.sent] == harness.admins.ids
    assert {kind for _, kind, _ in harness.notifications.sent} == {NotificationType.CUSTOM_REQUEST}
    assert submission.request.attachments[0].original_filename == "photo0.jpg"


async def test_a_submission_without_images_is_a_lead_too() -> None:
    harness = Harness()
    await harness.submit()
    assert harness.storage.files == {}
    assert len(harness.requests.added) == 1
    assert len(harness.notifications.sent) == 2


async def test_malware_in_the_third_file_stores_none_and_notifies_nobody() -> None:
    harness = Harness()
    with pytest.raises(AttachmentMalwareError) as caught:
        await harness.submit(_jpeg(), _jpeg(), _jpeg() + EICAR)
    assert caught.value.index == 2
    assert (harness.storage.puts, harness.requests.added) == (0, [])
    assert harness.notifications.sent == []


async def test_a_fake_image_is_rejected_before_anything_is_stored() -> None:
    harness = Harness()
    with pytest.raises(AttachmentRejectedError) as caught:
        await harness.submit(_jpeg(), b"%PDF-1.7 not an image")
    assert caught.value.index == 1
    assert (harness.storage.puts, harness.requests.added) == (0, [])


async def test_the_raw_upload_is_scanned_before_it_is_decoded() -> None:
    harness = Harness()
    upload = _jpeg()
    await harness.submit(upload)
    assert harness.scanner.scanned == [upload]
    assert upload not in harness.storage.files.values()


async def test_a_scanner_outage_stores_nothing() -> None:
    harness = Harness(scanner_up=False)
    with pytest.raises(ScannerUnavailableError):
        await harness.submit(_jpeg())
    assert (harness.storage.puts, harness.requests.added) == (0, [])


async def test_too_many_files_are_rejected_before_any_scan() -> None:
    harness = Harness()
    with pytest.raises(AttachmentRejectedError):
        await harness.submit(*[_jpeg()] * (MAX_ATTACHMENTS + 1))
    assert harness.scanner.scanned == []


async def test_a_storage_failure_on_the_second_file_deletes_the_first_and_inserts_nothing() -> None:
    harness = Harness(storage=MemoryStorage(fail_on_put=2))
    with pytest.raises(OSError):
        await harness.submit(_jpeg(), _jpeg())
    assert harness.storage.files == {}
    assert harness.requests.added == []
    assert harness.notifications.sent == []


async def test_an_insert_failure_deletes_every_stored_file() -> None:
    harness = Harness(insert_fails=True)
    with pytest.raises(RuntimeError):
        await harness.submit(_jpeg(), _jpeg())
    assert harness.storage.puts == 2
    assert harness.storage.files == {}
    assert harness.notifications.sent == []


async def test_a_notification_failure_keeps_the_request_and_its_files() -> None:
    """FR-15: "Notification failure does not remove the submitted request"."""
    harness = Harness(notify_fails=True)
    submission = await harness.submit(_jpeg(), _jpeg())
    assert submission.failed_notifications == len(harness.admins.ids)
    assert len(harness.requests.added) == 1
    assert len(harness.storage.files) == 2
