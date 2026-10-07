from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.engagement.domain.enums import NotificationType


@dataclass
class Notification:
    """One in-app message informing a user of a business event.

    The lifecycle is `UNREAD -> READ`, and per entities-and-business-rules.md it
    "may be represented by `read_at`" - which is how it is represented here, so
    there is no second status column that could disagree with the timestamp.

    There is no `updated_at`. `read_at` is the only mutable field, so a second
    mutation timestamp would carry no information the first does not, and
    database-design.md 12.3 does not define one.
    """

    id: UUID
    user_id: UUID
    type: NotificationType
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime

    @property
    def read(self) -> bool:
        """The API's `read` flag, derived rather than stored.

        `read_at` itself is not exposed in V1, but it is what the flag is
        computed from - so the two can never drift, which a stored boolean
        alongside a timestamp eventually would.
        """
        return self.read_at is not None
