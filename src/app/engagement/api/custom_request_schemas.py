from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.api.captcha import CaptchaToken
from app.api.text import Email, MultilineStr, PlainStr
from app.engagement.domain.custom_request import (
    ADMIN_NOTES_MAX,
    DESCRIPTION_MAX,
    DIMENSIONS_MAX,
    NAME_MAX,
    PHONE_MAX,
    PREFERENCE_MAX,
    TITLE_MAX,
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    check_quote,
)
from app.engagement.domain.enums import CustomRequestOutcome, CustomRequestStatus
from app.engagement.domain.exceptions import InvalidCustomRequestError, InvalidQuoteError


class CustomRequestCreate(BaseModel):
    """The text parts of the multipart form (api-endpoints.md 29.9); files are separate."""

    model_config = ConfigDict(extra="forbid")

    name: PlainStr = Field(max_length=NAME_MAX)
    email: Email
    phone: PlainStr = Field(max_length=PHONE_MAX)
    project_title: PlainStr = Field(max_length=TITLE_MAX)
    description: MultilineStr = Field(max_length=DESCRIPTION_MAX)
    preferred_material: PlainStr | None = Field(default=None, max_length=PREFERENCE_MAX)
    preferred_colour: PlainStr | None = Field(default=None, max_length=PREFERENCE_MAX)
    dimensions: PlainStr | None = Field(default=None, max_length=DIMENSIONS_MAX)
    captcha_token: CaptchaToken

    @model_validator(mode="after")
    def _domain_rules(self) -> "CustomRequestCreate":
        try:
            self.details()
        except InvalidCustomRequestError as exc:
            raise ValueError(str(exc)) from exc
        return self

    def details(self) -> CustomRequestDetails:
        return CustomRequestDetails.of(**self.model_dump(exclude={"captcha_token"}))


class CustomRequestReceipt(BaseModel):
    """Deliberately no attachment URLs or keys: attachments are admin-only (BR-111)."""

    id: UUID
    created_at: datetime


class CustomRequestAttachmentInfo(BaseModel):
    """Metadata only; the bytes come from the admin download route (BR-111)."""

    id: UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    expires_at: datetime
    created_at: datetime

    @classmethod
    def of(cls, attachment: CustomRequestAttachment) -> "CustomRequestAttachmentInfo":
        return cls(
            id=attachment.id,
            original_filename=attachment.original_filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            expires_at=attachment.expires_at,
            created_at=attachment.created_at,
        )


class CustomRequestSummary(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    project_title: str
    status: CustomRequestStatus
    quoted_amount_cents: int | None
    currency: str | None
    outcome: CustomRequestOutcome | None
    attachment_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, lead: CustomRequest) -> "CustomRequestSummary":
        return cls(
            **{
                name: getattr(lead, name) for name in cls.model_fields if name != "attachment_count"
            },
            attachment_count=len(lead.attachments),
        )


class CustomRequestDetail(BaseModel):
    """api-endpoints.md 23: the lead, its admin fields and its unexpired attachments."""

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
    attachments: list[CustomRequestAttachmentInfo]

    @classmethod
    def of(cls, lead: CustomRequest) -> "CustomRequestDetail":
        return cls(
            **{name: getattr(lead, name) for name in cls.model_fields if name != "attachments"},
            attachments=[CustomRequestAttachmentInfo.of(a) for a in lead.attachments],
        )


class CustomRequestPage(BaseModel):
    items: list[CustomRequestSummary]
    next_cursor: str | None


class CustomRequestTransition(BaseModel):
    """The server derives the outcome and currency (ADR-031); notes go through PATCH."""

    model_config = ConfigDict(extra="forbid")

    target_status: CustomRequestStatus
    quoted_amount_cents: StrictInt | None = None

    @model_validator(mode="after")
    def _quote_rules(self) -> "CustomRequestTransition":
        try:
            check_quote(self.target_status, self.quoted_amount_cents)
        except InvalidQuoteError as exc:
            raise ValueError(exc.reason) from exc
        return self


class CustomRequestAdminUpdate(BaseModel):
    """Notes only; status changes go through the transition route. Blank clears them."""

    model_config = ConfigDict(extra="forbid")

    admin_notes: MultilineStr | None = Field(max_length=ADMIN_NOTES_MAX)

    def notes(self) -> str | None:
        return (self.admin_notes or "").strip() or None


class CustomRequestFunnelAnalytics(BaseModel):
    """One cohort by submission date, `from` inclusive and `to` exclusive (VS-035)."""

    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(alias="from")
    to: datetime
    submitted: int
    contacted: int
    quoted: int
    won: int
    lost: int
    open: int
    quoted_total_cents: int
    won_total_cents: int
    currency: str
