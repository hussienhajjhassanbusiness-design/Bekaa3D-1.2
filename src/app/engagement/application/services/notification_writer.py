"""Validating and storing one in-app notification.

The logic behind the sanctioned write port. Other contexts call
`app.engagement.public.create_notification`, which binds this to the caller's
session; they must not import `NotificationModel`, `NotificationRepository`, or
write raw SQL against `notifications` - that rule is what keeps Engagement's
table Engagement's, and `tests/unit/engagement/test_notification_boundary.py`
enforces it.
"""

from typing import Any
from uuid import UUID

from app.engagement.application.ports import NotificationStore
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.domain.exceptions import InvalidNotificationPayloadError
from app.engagement.domain.payload import validate_payload


async def write_notification(
    notifications: NotificationStore,
    *,
    user_id: UUID,
    notification_type: NotificationType,
    payload: dict[str, Any],
) -> Notification:
    """Validate and insert one notification through `notifications`, which is
    bound to the caller's transaction. Does **not** commit; see
    `app.engagement.public.create_notification` for why."""
    if not isinstance(notification_type, NotificationType):
        # Not a payload problem, so it does not go in the payload error: passing
        # a bare string here would otherwise reach asyncpg and fail as an opaque
        # enum bind error at flush time, a long way from the caller.
        raise InvalidNotificationPayloadError(
            [
                "notification_type must be a NotificationType, got "
                f"{type(notification_type).__name__}"
            ]
        )

    validated = validate_payload(payload)
    return await notifications.add(
        user_id=user_id,
        notification_type=notification_type,
        payload=validated,
    )
