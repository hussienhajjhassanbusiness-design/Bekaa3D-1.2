from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.captcha import CaptchaToken
from app.api.text import Email, MultilineStr, PlainStr
from app.engagement.domain.custom_request import (
    DESCRIPTION_MAX,
    DIMENSIONS_MAX,
    NAME_MAX,
    PHONE_MAX,
    PREFERENCE_MAX,
    TITLE_MAX,
    CustomRequestDetails,
)
from app.engagement.domain.exceptions import InvalidCustomRequestError


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
