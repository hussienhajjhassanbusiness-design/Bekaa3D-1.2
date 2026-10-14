from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.text import MultilineStr, PlainStr
from app.core.phone import INPUT_MAX as PHONE_INPUT_MAX
from app.identity.domain.address import (
    AREA_MAX,
    CITY_MAX,
    LABEL_MAX,
    LANDMARK_NOTES_MAX,
    RECIPIENT_NAME_MAX,
    STREET_MAX,
    Address,
)
from app.identity.domain.enums import Governorate

_DETAIL_FIELDS = (
    "label",
    "recipient_name",
    "phone",
    "governorate",
    "city",
    "area",
    "street",
    "landmark_notes",
)


class AddressCreate(BaseModel):
    """api-endpoints.md 29.3; `landmark_notes` is required (SRS 14.4, VS-026 Q1)."""

    model_config = ConfigDict(extra="forbid")

    label: PlainStr = Field(max_length=LABEL_MAX)
    recipient_name: PlainStr = Field(max_length=RECIPIENT_NAME_MAX)
    phone: PlainStr = Field(
        max_length=PHONE_INPUT_MAX, description="Lebanese; stored and returned as E.164."
    )
    governorate: Governorate
    city: PlainStr = Field(max_length=CITY_MAX)
    area: PlainStr | None = Field(default=None, max_length=AREA_MAX)
    street: PlainStr | None = Field(default=None, max_length=STREET_MAX)
    landmark_notes: MultilineStr = Field(max_length=LANDMARK_NOTES_MAX)
    is_default: bool = Field(
        default=False, description="A user's first live address is the default regardless."
    )

    def detail_values(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _DETAIL_FIELDS}


class AddressUpdate(BaseModel):
    """Any subset of the create fields; `null` clears `area` or `street`."""

    model_config = ConfigDict(extra="forbid")

    label: PlainStr | None = Field(default=None, max_length=LABEL_MAX)
    recipient_name: PlainStr | None = Field(default=None, max_length=RECIPIENT_NAME_MAX)
    phone: PlainStr | None = Field(default=None, max_length=PHONE_INPUT_MAX)
    governorate: Governorate | None = None
    city: PlainStr | None = Field(default=None, max_length=CITY_MAX)
    area: PlainStr | None = Field(default=None, max_length=AREA_MAX)
    street: PlainStr | None = Field(default=None, max_length=STREET_MAX)
    landmark_notes: MultilineStr | None = Field(default=None, max_length=LANDMARK_NOTES_MAX)
    is_default: bool | None = Field(
        default=None, description="`true` makes it the default; `false` clears it."
    )

    @model_validator(mode="after")
    def _not_empty(self) -> "AddressUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self

    def changes(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in _DETAIL_FIELDS
            if field in self.model_fields_set
        }


class AddressRead(BaseModel):
    id: UUID
    label: str
    recipient_name: str
    phone: str
    governorate: Governorate
    city: str
    area: str | None
    street: str | None
    landmark_notes: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, address: Address) -> "AddressRead":
        details = address.details
        return cls(
            id=address.id,
            label=details.label,
            recipient_name=details.recipient_name,
            phone=details.phone,
            governorate=details.governorate,
            city=details.city,
            area=details.area,
            street=details.street,
            landmark_notes=details.landmark_notes,
            is_default=address.is_default,
            created_at=address.created_at,
            updated_at=address.updated_at,
        )


class AddressList(BaseModel):
    """Every live address, default first; at most `MAX_LIVE_ADDRESSES`."""

    items: list[AddressRead]
