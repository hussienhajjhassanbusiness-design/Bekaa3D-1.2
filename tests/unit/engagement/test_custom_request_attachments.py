"""VS-034: attachment caps, display filenames, expiry and the admin notification payload."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.engagement.domain.custom_request import (
    FALLBACK_FILENAME,
    FILENAME_MAX,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    CustomRequest,
    admin_notification_payload,
    attachment_expiry,
    check_attachment_count,
    check_attachment_size,
    safe_filename,
)
from app.engagement.domain.enums import CustomRequestStatus
from app.engagement.domain.exceptions import AttachmentRejectedError
from app.engagement.domain.payload import validate_payload


@pytest.mark.parametrize("count", [0, 1, MAX_ATTACHMENTS])
def test_zero_to_five_attachments_are_allowed(count: int) -> None:
    check_attachment_count(count)


def test_a_sixth_attachment_is_rejected() -> None:
    with pytest.raises(AttachmentRejectedError):
        check_attachment_count(MAX_ATTACHMENTS + 1)


@pytest.mark.parametrize("size", [1, MAX_ATTACHMENT_BYTES])
def test_sizes_within_the_cap_pass(size: int) -> None:
    check_attachment_size(0, size)


@pytest.mark.parametrize("size", [0, MAX_ATTACHMENT_BYTES + 1])
def test_empty_or_oversized_files_are_rejected_with_their_index(size: int) -> None:
    with pytest.raises(AttachmentRejectedError) as caught:
        check_attachment_size(3, size)
    assert caught.value.index == 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("photo.jpg", "photo.jpg"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\rima\\lamp.png", "lamp.png"),
        ("bad\x00na\x1bme\u202e.jpg", "badname.jpg"),
        ("  spaced.webp  ", "spaced.webp"),
        ("", FALLBACK_FILENAME),
        (None, FALLBACK_FILENAME),
        ("dir/", FALLBACK_FILENAME),
        ("\x07\x08", FALLBACK_FILENAME),
    ],
)
def test_safe_filename_keeps_only_a_printable_base_name(raw: str | None, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_safe_filename_is_capped() -> None:
    assert len(safe_filename("a" * 1000 + ".jpg")) == FILENAME_MAX


def test_expiry_is_submission_time_plus_retention() -> None:
    submitted = datetime(2026, 10, 17, 12, tzinfo=UTC)
    assert attachment_expiry(submitted, 7_776_000) == submitted + timedelta(days=90)


def test_the_admin_payload_names_the_request_and_title_only() -> None:
    now = datetime.now(UTC)
    request = CustomRequest(
        id=uuid.uuid4(),
        name="Rima",
        email="rima@example.com",
        phone="+961 3 123 456",
        project_title="Cedar lamp",
        description="A lamp.",
        preferred_material=None,
        preferred_colour=None,
        dimensions=None,
        status=CustomRequestStatus.NEW,
        quoted_amount_cents=None,
        currency=None,
        outcome=None,
        admin_notes=None,
        contacted_at=None,
        quoted_at=None,
        completed_at=None,
        closed_at=None,
        created_at=now,
        updated_at=now,
        attachments=(),
    )
    payload = admin_notification_payload(request)
    validate_payload(payload)
    assert payload == {
        "event": "custom_request.submitted",
        "custom_request_id": str(request.id),
        "project_title": "Cedar lamp",
        "title": "New Bring Your Idea request: Cedar lamp",
    }
