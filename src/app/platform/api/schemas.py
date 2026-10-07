from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.platform.domain.entities import AuditLogEntry, Setting
from app.platform.domain.enums import SettingType
from app.platform.domain.settings_registry import SettingDefinition, definition_for


class SettingUpdate(BaseModel):
    """api-endpoints.md 29.16: a single `value`, validated server-side against
    the key's declared type and range.

    `Any` rather than a union, deliberately. The wire type depends on the key -
    a boolean here, a money object there - so the shape cannot be decided by
    this schema, only by the registry once the key is known. Pydantic's job here
    is to reject a malformed *envelope*: a missing `value`, or extra fields
    under `extra="forbid"`. A bad *value* is a different failure with a
    different code (422 SETTING_INVALID), raised by the registry.
    """

    model_config = ConfigDict(extra="forbid")

    value: Any


class MoneyRead(BaseModel):
    """The API's standard money shape (api-endpoints.md 2, ADR-008). Never a
    float."""

    amount_cents: int
    currency: str


class SettingRead(BaseModel):
    """One setting, with the validation metadata an admin UI needs to render the
    right editor.

    `unit`, `minimum`, `maximum`, `nullable` and `is_public` are read from the
    code registry rather than stored as columns: they are rules, not data, and
    keeping them out of the table means widening a range is a reviewed code
    change instead of a `PATCH` somebody could make at runtime.
    """

    key: str
    type: SettingType
    value: Any
    description: str | None
    unit: str | None
    minimum: int | None
    maximum: int | None
    nullable: bool
    is_public: bool
    updated_at: datetime
    updated_by: UUID | None

    @classmethod
    def from_setting(
        cls, setting: Setting, definition: SettingDefinition | None = None
    ) -> "SettingRead":
        spec = definition or definition_for(setting.key)
        return cls(
            key=setting.key,
            type=setting.type,
            value=setting.value,
            description=setting.description,
            unit=spec.unit,
            minimum=spec.minimum,
            maximum=spec.maximum,
            nullable=spec.nullable,
            is_public=spec.is_public,
            updated_at=setting.updated_at,
            updated_by=setting.updated_by,
        )


class SettingPage(BaseModel):
    """The project's standard cursor page (api-endpoints.md 2.1):
    `next_cursor = null` means there is no next page."""

    items: list[SettingRead]
    next_cursor: str | None


class AuditLogRead(BaseModel):
    """One audit entry, as the viewer shows it (api-endpoints.md 26).

    `ip_hash` is deliberately absent. It is a salted SHA-256 of an address, and
    the IPv4 space is small enough that anyone holding the salt can reverse it
    by brute force (CLAUDE.md, local secrets) - while a person reading the log
    learns nothing from 64 hex characters. It stays in the table for
    correlation in the database, not on the API. `before_data`/`after_data`
    are returned as written: sensitive values are redacted at write time.
    """

    id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    request_id: str | None
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: AuditLogEntry) -> "AuditLogRead":
        return cls(
            id=entry.id,
            actor_user_id=entry.actor_user_id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            before_data=entry.before_data,
            after_data=entry.after_data,
            request_id=entry.request_id,
            created_at=entry.created_at,
        )


class AuditLogPage(BaseModel):
    """The standard cursor page (api-endpoints.md 2.1)."""

    items: list[AuditLogRead]
    next_cursor: str | None


class PublicSettingsRead(BaseModel):
    """The five allowlisted settings, and nothing else.

    This is a **fixed schema, not a dictionary**, and that is the whole security
    design. A new row in the `settings` table has no field here to land in, so a
    setting cannot become public by being added - it becomes public only when
    someone edits this class and its registry entry together, in a reviewed
    change. The alternative shape - read every row and filter - leaks the moment
    a filter is forgotten.

    Every field except `accepting_orders` is nullable because the real values
    are still awaited from the client (SRS 30.2). Null means "not configured";
    the frontend hides the element rather than showing invented data.
    """

    accepting_orders: bool
    free_shipping_threshold: MoneyRead | None
    pickup_address: str | None
    pickup_hours: str | None
    whatsapp_number: str | None
