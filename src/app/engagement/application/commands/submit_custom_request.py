"""Bring Your Idea submission (FR-15, ADR-021, ADR-030). Captcha and rate limits run before
this; it screens every file before storing any, and removes stored files if the lead fails."""

import contextlib
import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.engagement.application.ports import (
    AdministratorDirectory,
    CustomRequestStore,
    NotificationStore,
)
from app.engagement.application.services.notification_writer import write_notification
from app.engagement.domain.custom_request import (
    STORAGE_PREFIX,
    CustomRequest,
    CustomRequestDetails,
    NewAttachment,
    admin_notification_payload,
    attachment_expiry,
    check_attachment_count,
    check_attachment_size,
    safe_filename,
)
from app.engagement.domain.enums import NotificationType
from app.engagement.domain.exceptions import AttachmentMalwareError, AttachmentRejectedError
from app.integrations.images.ports import ImageRejectedError, ImageSanitizerPort, SanitizedImage
from app.integrations.scanning.ports import MalwareScannerPort
from app.integrations.storage.ports import StoragePort


@dataclass(frozen=True)
class AttachmentUpload:
    """Raw bytes as received; `filename` is the client's and is display-only."""

    filename: str | None
    data: bytes


@dataclass(frozen=True)
class CustomRequestSubmission:
    request: CustomRequest
    failed_notifications: int


class SubmitCustomRequest:
    def __init__(
        self,
        requests: CustomRequestStore,
        notifications: NotificationStore,
        administrators: AdministratorDirectory,
        *,
        storage: StoragePort,
        scanner: MalwareScannerPort,
        sanitizer: ImageSanitizerPort,
    ) -> None:
        self._requests = requests
        self._notifications = notifications
        self._administrators = administrators
        self._storage = storage
        self._scanner = scanner
        self._sanitizer = sanitizer

    async def execute(
        self,
        details: CustomRequestDetails,
        uploads: Sequence[AttachmentUpload],
        *,
        retention_seconds: int,
    ) -> CustomRequestSubmission:
        check_attachment_count(len(uploads))
        screened = [await self._screen(index, upload) for index, upload in enumerate(uploads)]
        submitted_at = datetime.now(UTC)
        stored: list[str] = []
        try:
            attachments = []
            for upload, clean in zip(uploads, screened, strict=True):
                key = f"{STORAGE_PREFIX}{uuid.uuid4()}.{clean.extension}"
                await self._storage.put(key, clean.data)
                stored.append(key)
                attachments.append(_attachment(key, upload, clean))
            request = await self._requests.add(
                details,
                attachments,
                submitted_at=submitted_at,
                expires_at=attachment_expiry(submitted_at, retention_seconds),
            )
        except Exception:
            await self._remove(stored)
            raise
        return CustomRequestSubmission(request, await self._notify_administrators(request))

    async def _screen(self, index: int, upload: AttachmentUpload) -> SanitizedImage:
        """ADR-021 order: size, scan the raw bytes, then sniff, decode and re-encode."""
        check_attachment_size(index, len(upload.data))
        verdict = await self._scanner.scan(upload.data)
        if not verdict.clean:
            raise AttachmentMalwareError(index, verdict.signature)
        try:
            return await self._sanitizer.sanitize(upload.data)
        except ImageRejectedError as exc:
            raise AttachmentRejectedError(exc.reason, index=index) from exc

    async def _notify_administrators(self, request: CustomRequest) -> int:
        """FR-15: a failed notification never removes the request. Returns how many failed;
        the store must isolate each insert (a savepoint) so the transaction stays usable."""
        payload, failed = admin_notification_payload(request), 0
        for admin_id in await self._administrators.active_administrator_ids():
            try:
                await write_notification(
                    self._notifications,
                    user_id=admin_id,
                    notification_type=NotificationType.CUSTOM_REQUEST,
                    payload=payload,
                )
            except Exception:
                failed += 1
        return failed

    async def _remove(self, keys: list[str]) -> None:
        """Best effort: a file left behind is unreferenced, so `reap_orphan_files` takes it."""
        for key in keys:
            with contextlib.suppress(Exception):
                await self._storage.delete(key)


def _attachment(key: str, upload: AttachmentUpload, clean: SanitizedImage) -> NewAttachment:
    return NewAttachment(
        storage_key=key,
        original_filename=safe_filename(upload.filename),
        mime_type=clean.content_type,
        size_bytes=len(clean.data),
        checksum=hashlib.sha256(clean.data).hexdigest(),
    )
