"""Bring Your Idea submissions (SRS 13, FR-15). A lead, never a transaction (BR-112)."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.engagement.domain.contact_message import EMAIL_MAX, phone_shaped
from app.engagement.domain.enums import CustomRequestOutcome, CustomRequestStatus
from app.engagement.domain.exceptions import (
    AttachmentRejectedError,
    InvalidCustomRequestError,
    InvalidCustomRequestTransitionError,
    InvalidQuoteError,
)

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

ADMIN_NOTES_MAX = 5000
# A recorded quote, never a charge (BR-112); zero is refused as a likely typo (ADR-031).
QUOTE_MIN_CENTS = 1
QUOTE_MAX_CENTS = 100_000_000
QUOTE_CURRENCY = "USD"
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

_S = CustomRequestStatus
# SRS 20.7: the only edges; `closed` and `lost` are terminal.
PIPELINE: dict[CustomRequestStatus, frozenset[CustomRequestStatus]] = {
    _S.NEW: frozenset({_S.CONTACTED}),
    _S.CONTACTED: frozenset({_S.QUOTED, _S.LOST}),
    _S.QUOTED: frozenset({_S.IN_PROGRESS, _S.LOST}),
    _S.IN_PROGRESS: frozenset({_S.COMPLETED}),
    _S.COMPLETED: frozenset({_S.CLOSED}),
    _S.CLOSED: frozenset(),
    _S.LOST: frozenset(),
}
_STAMPS = {
    _S.CONTACTED: "contacted_at",
    _S.QUOTED: "quoted_at",
    _S.COMPLETED: "completed_at",
    _S.CLOSED: "closed_at",
    _S.LOST: "closed_at",
}
# Work starts only after an off-platform agreement, so `in_progress` is the win (ADR-031).
_OUTCOMES = {_S.IN_PROGRESS: CustomRequestOutcome.WON, _S.LOST: CustomRequestOutcome.LOST}


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
    """One Bring Your Idea submission and its pipeline state (glossary: Custom Request)."""

    id: UUID
    name: str
    email: str
    phone: str
    project_title: str
    description: str
    preferred_material: str | None
    preferred_colour: str | None
    dimensions: str | None
    status: CustomRequestStatus
    quoted_amount_cents: int | None
    currency: str | None
    outcome: CustomRequestOutcome | None
    admin_notes: str | None
    contacted_at: datetime | None
    quoted_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attachments: tuple[CustomRequestAttachment, ...]


@dataclass(frozen=True)
class PipelineChange:
    """What one transition writes: the status, at most one `*_at` stamp, outcome, quote."""

    status: CustomRequestStatus
    stamp: str | None
    outcome: CustomRequestOutcome | None
    quoted_amount_cents: int | None


def check_quote(target: CustomRequestStatus, quoted_amount_cents: int | None) -> None:
    """An amount is required on `quoted` and meaningless anywhere else (BR-114)."""
    if target is not _S.QUOTED:
        if quoted_amount_cents is not None:
            raise InvalidQuoteError("an amount is recorded only when moving to quoted")
    elif quoted_amount_cents is None:
        raise InvalidQuoteError("moving to quoted requires quoted_amount_cents")
    elif not QUOTE_MIN_CENTS <= quoted_amount_cents <= QUOTE_MAX_CENTS:
        raise InvalidQuoteError(
            f"quoted_amount_cents must be {QUOTE_MIN_CENTS} to {QUOTE_MAX_CENTS}"
        )


def plan_transition(
    current: CustomRequestStatus,
    target: CustomRequestStatus,
    quoted_amount_cents: int | None = None,
) -> PipelineChange:
    if target not in PIPELINE[current]:
        raise InvalidCustomRequestTransitionError(current, target)
    check_quote(target, quoted_amount_cents)
    return PipelineChange(
        status=target,
        stamp=_STAMPS.get(target),
        outcome=_OUTCOMES.get(target),
        quoted_amount_cents=quoted_amount_cents,
    )


def is_expired(attachment: CustomRequestAttachment, now: datetime) -> bool:
    """The purge job's boundary (`expires_at <= now`), so nothing outlives it here."""
    return attachment.expires_at <= now


def download_filename(original: str, mime_type: str) -> str:
    """The display name with the extension of the bytes actually stored (ADR-031)."""
    stem = safe_filename(original)
    if "." in stem.strip("."):
        stem = stem.rsplit(".", 1)[0].strip() or FALLBACK_FILENAME
    return f"{stem}.{_EXTENSIONS.get(mime_type, 'bin')}"


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
