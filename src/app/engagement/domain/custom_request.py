"""Bring Your Idea submissions (SRS 13, FR-15). A lead, never a transaction (BR-112)."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.engagement.domain.contact_message import EMAIL_MAX, phone_shaped
from app.engagement.domain.enums import CustomRequestStatus
from app.engagement.domain.exceptions import AttachmentRejectedError, InvalidCustomRequestError

NAME_MAX = 100
PHONE_MAX = 32
TITLE_MAX = 200
DESCRIPTION_MAX = 5000
PREFERENCE_MAX = 100
DIMENSIONS_MAX = 200

# Security bounds, code constants like ADR-021's (ADR-030): not business settings.
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
FILENAME_MAX = 255
FALLBACK_FILENAME = "image"
STORAGE_PREFIX = "custom-requests/"
NOTIFICATION_EVENT = "custom_request.submitted"


@dataclass(frozen=True)
class CustomRequestDetails:
    """What a visitor submits; trimmed, with blank optionals as None (SRS 13.2)."""

    name: str
    email: str
    phone: str
    project_title: str
    description: str
    preferred_material: str | None
    preferred_colour: str | None
    dimensions: str | None

    @classmethod
    def of(
        cls,
        *,
        name: str,
        email: str,
        phone: str,
        project_title: str,
        description: str,
        preferred_material: str | None = None,
        preferred_colour: str | None = None,
        dimensions: str | None = None,
    ) -> "CustomRequestDetails":
        details = cls(
            name=name.strip(),
            email=email.strip(),
            phone=phone.strip(),
            project_title=project_title.strip(),
            description=description.strip(),
            preferred_material=_optional(preferred_material),
            preferred_colour=_optional(preferred_colour),
            dimensions=_optional(dimensions),
        )
        details._check()
        return details

    def _check(self) -> None:
        required = (
            ("name", self.name, NAME_MAX),
            ("project_title", self.project_title, TITLE_MAX),
            ("description", self.description, DESCRIPTION_MAX),
        )
        problems = [field for field, value, most in required if not 1 <= len(value) <= most]
        if not 3 <= len(self.email) <= EMAIL_MAX or "@" not in self.email[1:]:
            problems.append("email")
        if len(self.phone) > PHONE_MAX or not phone_shaped(self.phone):
            problems.append("phone")
        optional = (
            ("preferred_material", self.preferred_material, PREFERENCE_MAX),
            ("preferred_colour", self.preferred_colour, PREFERENCE_MAX),
            ("dimensions", self.dimensions, DIMENSIONS_MAX),
        )
        problems += [field for field, value, most in optional if value and len(value) > most]
        if problems:
            raise InvalidCustomRequestError(problems)


@dataclass(frozen=True)
class NewAttachment:
    """A screened, re-encoded image already written to private storage."""

    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum: str


@dataclass(frozen=True)
class CustomRequestAttachment:
    id: UUID
    custom_request_id: UUID
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum: str
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class CustomRequest:
    """One Bring Your Idea submission (glossary: Custom Request)."""

    id: UUID
    project_title: str
    status: CustomRequestStatus
    created_at: datetime
    attachments: tuple[CustomRequestAttachment, ...]


def check_attachment_count(count: int) -> None:
    if count > MAX_ATTACHMENTS:
        raise AttachmentRejectedError(f"at most {MAX_ATTACHMENTS} images may be attached")


def check_attachment_size(index: int, size: int) -> None:
    if not 1 <= size <= MAX_ATTACHMENT_BYTES:
        raise AttachmentRejectedError(
            f"an image must be 1 byte to {MAX_ATTACHMENT_BYTES} bytes", index=index
        )


def safe_filename(raw: str | None) -> str:
    """For display only, never a path: the base name, no control characters, capped."""
    base = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    printable = "".join(c for c in base if not unicodedata.category(c).startswith("C"))
    return printable.strip()[:FILENAME_MAX].strip() or FALLBACK_FILENAME


def attachment_expiry(submitted_at: datetime, retention_seconds: int) -> datetime:
    return submitted_at + timedelta(seconds=retention_seconds)


def admin_notification_payload(request: CustomRequest) -> dict[str, Any]:
    """No email, phone or name: the payload is rendered in a browser (notification contract)."""
    return {
        "event": NOTIFICATION_EVENT,
        "custom_request_id": str(request.id),
        "project_title": request.project_title,
        "title": f"New Bring Your Idea request: {request.project_title}",
    }


def _optional(value: str | None) -> str | None:
    return (value or "").strip() or None
