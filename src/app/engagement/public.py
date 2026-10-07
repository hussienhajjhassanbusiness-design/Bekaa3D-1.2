"""Engagement's published surface for other bounded contexts.

Another context may import from here or from `app.engagement.application.ports`,
and from nowhere else in Engagement (enforced by
`tests/unit/test_deep_architecture.py`).
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.application.services.notification_writer import write_notification
from app.engagement.domain.entities import Notification
from app.engagement.domain.enums import NotificationType
from app.engagement.infrastructure.repositories import NotificationRepository

__all__ = ["NotificationType", "create_notification"]


async def create_notification(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_type: NotificationType,
    payload: dict[str, Any],
) -> Notification:
    """Validate and insert one notification. Does **not** commit.

    The caller's `AsyncSession` is taken as an argument rather than opened here,
    which is the same shape VS-007's settings reader uses and it is the whole
    point of the port. A business event and the notification announcing it land
    in one transaction:

        business mutation
        create_notification(...)
        email outbox insert, if the event also warrants email
        COMMIT

    So if the payment rolls back, the notification announcing it rolls back
    with it, and no customer is ever told about something that did not happen.
    A service that opened its own session and committed could not offer that -
    it would commit the announcement of a change that was still able to fail.

    There is no message broker, no event bus and no background notification
    worker. An in-app notification is a row; once the transaction commits it is
    already delivered, because "delivery" here is the customer reading their own
    table. That is what distinguishes it from email, which leaves the system.
    """
    return await write_notification(
        NotificationRepository(session),
        user_id=user_id,
        notification_type=notification_type,
        payload=payload,
    )
