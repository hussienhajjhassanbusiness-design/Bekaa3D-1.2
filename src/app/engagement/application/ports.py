"""Engagement's repository port. A pure `Protocol`: the application layer
depends on this, never on `app.engagement.infrastructure` (BUG-41)."""

from typing import Any, Protocol
from uuid import UUID

from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType


class NotificationStore(Protocol):
    async def add(
        self,
        *,
        user_id: UUID,
        notification_type: NotificationType,
        payload: dict[str, Any],
    ) -> Notification: ...
