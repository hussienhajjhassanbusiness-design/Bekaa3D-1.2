from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.phone import InvalidPhoneNumberError, normalise_lebanese_phone
from app.core.text import has_control_characters
from app.identity.domain.enums import Governorate
from app.identity.domain.exceptions import AddressLimitReachedError, InvalidAddressError

LABEL_MAX = 50
RECIPIENT_NAME_MAX = 100
CITY_MAX = 100
AREA_MAX = 100
STREET_MAX = 200
LANDMARK_NOTES_MAX = 500
# The list is hard-limited rather than paginated (api-endpoints.md rule 10, VS-026 Q6).
MAX_LIVE_ADDRESSES = 20

_REQUIRED = {
    "label": LABEL_MAX,
    "recipient_name": RECIPIENT_NAME_MAX,
    "city": CITY_MAX,
    # Lebanese addressing is landmark-based, so the notes are required (SRS 14.4, VS-026 Q1).
    "landmark_notes": LANDMARK_NOTES_MAX,
}
_OPTIONAL = {"area": AREA_MAX, "street": STREET_MAX}


@dataclass(frozen=True)
class AddressDetails:
    """The editable fields, trimmed, blank optionals as None, phone in E.164 (FR-03)."""

    label: str
    recipient_name: str
    phone: str
    governorate: Governorate
    city: str
    area: str | None
    street: str | None
    landmark_notes: str

    @classmethod
    def of(cls, **raw: Any) -> "AddressDetails":
        problems: list[str] = []
        values: dict[str, Any] = {}
        for field, limit in _REQUIRED.items():
            values[field] = _text(raw[field], limit, required=True, problems=problems, name=field)
        for field, limit in _OPTIONAL.items():
            values[field] = _text(raw[field], limit, required=False, problems=problems, name=field)
        try:
            values["phone"] = normalise_lebanese_phone(raw["phone"])
        except InvalidPhoneNumberError:
            problems.append("phone")
        try:
            values["governorate"] = Governorate(raw["governorate"])
        except ValueError:
            problems.append("governorate")
        if problems:
            raise InvalidAddressError(sorted(problems))
        return cls(**values)

    def changed(self, **changes: Any) -> "AddressDetails":
        """A partial update, re-validated as a whole."""
        return AddressDetails.of(**(asdict(self) | changes))


@dataclass
class Address:
    """A customer's saved delivery address (glossary: Delivery Address)."""

    id: UUID
    user_id: UUID
    details: AddressDetails
    is_default: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


def check_capacity(live_count: int) -> None:
    if live_count >= MAX_LIVE_ADDRESSES:
        raise AddressLimitReachedError(MAX_LIVE_ADDRESSES)


def becomes_default(*, requested: bool, live_count: int) -> bool:
    """A user's first live address is always the default; later ones only on request."""
    return requested or live_count == 0


def _text(value: Any, limit: int, *, required: bool, problems: list[str], name: str) -> str | None:
    text = value.strip() if isinstance(value, str) else None
    if not text:
        if required:
            problems.append(name)
        return None
    if len(text) > limit or has_control_characters(
        text, allow_line_breaks=name == "landmark_notes"
    ):
        problems.append(name)
    return text
