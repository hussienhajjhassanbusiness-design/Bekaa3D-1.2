from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType


class NotificationUpdate(BaseModel):
    """api-endpoints.md 29.8: a single `read` flag.

    `extra="forbid"` per the project's request-schema convention, so a client
    that sends `{"read": true, "read_at": "..."}` is told it is wrong rather
    than having the extra field silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    read: bool


class NotificationRead(BaseModel):
    """One notification as the customer sees it.

    `read_at` is **not** exposed in V1. The API contract that
    api-endpoints.md 29.8 defines is a boolean `read`, and publishing the
    timestamp as well would make a second, redundant representation of the same
    state that clients could start depending on. The column still exists -
    it is what `read` is derived from, and it records the first-read moment.
    """

    id: UUID
    type: NotificationType
    payload: dict[str, Any]
    read: bool
    created_at: datetime

    @classmethod
    def from_notification(cls, notification: Notification) -> "NotificationRead":
        return cls(
            id=notification.id,
            type=notification.type,
            payload=notification.payload,
            # Derived on every render, never stored, so it cannot disagree with
            # the column it describes.
            read=notification.read,
            created_at=notification.created_at,
        )


class NotificationPage(BaseModel):
    """The project's standard cursor page (api-endpoints.md 2.1):
    `next_cursor = null` means there is no next page."""

    items: list[NotificationRead]
    next_cursor: str | None
