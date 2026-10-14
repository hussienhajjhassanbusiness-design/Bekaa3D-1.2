from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.captcha import CaptchaToken
from app.api.text import Email, MultilineStr, PlainStr
from app.engagement.domain.contact_message import (
    MESSAGE_MAX,
    NAME_MAX,
    PHONE_MAX,
    SUBJECT_MAX,
    ContactDetails,
    ContactMessage,
)
from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.domain.exceptions import InvalidContactDetailsError


class ContactMessageCreate(BaseModel):
    """api-endpoints.md 29: validated before the captcha, so a bad form costs no quota."""

    model_config = ConfigDict(extra="forbid")

    name: PlainStr = Field(max_length=NAME_MAX)
    email: Email
    phone: PlainStr | None = Field(default=None, max_length=PHONE_MAX)
    subject: PlainStr | None = Field(default=None, max_length=SUBJECT_MAX)
    message: MultilineStr = Field(max_length=MESSAGE_MAX)
    captcha_token: CaptchaToken

    @model_validator(mode="after")
    def _domain_rules(self) -> "ContactMessageCreate":
        try:
            self.details()
        except InvalidContactDetailsError as exc:
            raise ValueError(str(exc)) from exc
        return self

    def details(self) -> ContactDetails:
        return ContactDetails.of(
            name=self.name,
            email=self.email,
            phone=self.phone,
            subject=self.subject,
            message=self.message,
        )


class ContactMessageReceipt(BaseModel):
    id: UUID
    created_at: datetime


class ContactMessageDetail(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    subject: str | None
    message: str
    status: ContactMessageStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, message: ContactMessage) -> "ContactMessageDetail":
        return cls(
            id=message.id,
            name=message.name,
            email=message.email,
            phone=message.phone,
            subject=message.subject,
            message=message.message,
            status=message.status,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )


class ContactMessagePage(BaseModel):
    items: list[ContactMessageDetail]
    next_cursor: str | None


class ContactMessageAdminUpdate(BaseModel):
    """Status only, forward only (VS-033); the reply itself happens outside the system."""

    model_config = ConfigDict(extra="forbid")

    status: ContactMessageStatus
