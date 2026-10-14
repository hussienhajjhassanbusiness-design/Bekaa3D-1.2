"""Engagement's repository ports. A pure `Protocol`: the application layer
depends on this, never on `app.engagement.infrastructure` (BUG-41)."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.engagement.domain.contact_message import ContactDetails, ContactMessage
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import ContactMessageStatus, NotificationType


class NotificationStore(Protocol):
    async def add(
        self,
        *,
        user_id: UUID,
        notification_type: NotificationType,
        payload: dict[str, Any],
    ) -> Notification: ...


class ContactMessageStore(Protocol):
    async def add(self, details: ContactDetails) -> ContactMessage: ...

    async def get(self, message_id: UUID) -> ContactMessage | None: ...

    async def get_for_update(self, message_id: UUID) -> ContactMessage | None: ...

    async def set_status(
        self, message_id: UUID, status: ContactMessageStatus
    ) -> ContactMessage: ...

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[ContactMessageStatus, datetime, UUID] | None,
        status: ContactMessageStatus | None,
        created_after: datetime | None,
        created_before: datetime | None,
        email: str | None,
    ) -> list[ContactMessage]: ...
