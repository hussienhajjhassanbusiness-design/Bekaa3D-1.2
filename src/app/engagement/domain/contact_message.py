import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.domain.exceptions import (
    InvalidContactDetailsError,
    InvalidContactMessageTransitionError,
)

NAME_MAX = 100
EMAIL_MAX = 254
PHONE_MAX = 32
SUBJECT_MAX = 200
MESSAGE_MAX = 5000

_ORDER = list(ContactMessageStatus)
# Free-form but phone-shaped: an optional +, digits and common separators, 6+ digits.
PHONE_PATTERN = re.compile(r"\+?[0-9 ().\-]{6,31}")
PHONE_MIN_DIGITS = 6


@dataclass(frozen=True)
class ContactDetails:
    """What a visitor submits; trimmed, with blank optionals as None (FR-16)."""

    name: str
    email: str
    phone: str | None
    subject: str | None
    message: str

    @classmethod
    def of(
        cls, *, name: str, email: str, phone: str | None, subject: str | None, message: str
    ) -> "ContactDetails":
        details = cls(
            name=name.strip(),
            email=email.strip(),
            phone=(phone or "").strip() or None,
            subject=(subject or "").strip() or None,
            message=message.strip(),
        )
        details._check()
        return details

    def _check(self) -> None:
        problems = []
        if not 1 <= len(self.name) <= NAME_MAX:
            problems.append("name")
        if not 3 <= len(self.email) <= EMAIL_MAX or "@" not in self.email[1:]:
            problems.append("email")
        if self.phone is not None and not _phone_shaped(self.phone):
            problems.append("phone")
        if self.subject is not None and len(self.subject) > SUBJECT_MAX:
            problems.append("subject")
        if not 1 <= len(self.message) <= MESSAGE_MAX:
            problems.append("message")
        if problems:
            raise InvalidContactDetailsError(problems)


@dataclass
class ContactMessage:
    """A visitor enquiry from the contact form (glossary: Contact Message)."""

    id: UUID
    name: str
    email: str
    phone: str | None
    subject: str | None
    message: str
    status: ContactMessageStatus
    created_at: datetime
    updated_at: datetime


def can_transition(current: ContactMessageStatus, target: ContactMessageStatus) -> bool:
    """Forward only, skips allowed (VS-033 Q6); staying put is a no-op, not a move."""
    return _ORDER.index(target) >= _ORDER.index(current)


def check_transition(current: ContactMessageStatus, target: ContactMessageStatus) -> None:
    if not can_transition(current, target):
        raise InvalidContactMessageTransitionError(current, target)


def _phone_shaped(phone: str) -> bool:
    digits = sum(char in "0123456789" for char in phone)
    return PHONE_PATTERN.fullmatch(phone) is not None and digits >= PHONE_MIN_DIGITS
