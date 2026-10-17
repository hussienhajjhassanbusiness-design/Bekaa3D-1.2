"""Engagement's repository ports. A pure `Protocol`: the application layer
depends on this, never on `app.engagement.infrastructure` (BUG-41)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.engagement.domain.contact_message import ContactDetails, ContactMessage
from app.engagement.domain.custom_request import (
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    NewAttachment,
)
from app.engagement.domain.entities import Notification, WishlistItem
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


class CustomRequestStore(Protocol):
    async def add(
        self,
        details: CustomRequestDetails,
        attachments: Sequence[NewAttachment],
        *,
        submitted_at: datetime,
        expires_at: datetime,
    ) -> CustomRequest: ...

    async def lock_expired_attachments(
        self, *, now: datetime, limit: int
    ) -> list[CustomRequestAttachment]:
        """`expires_at <= now`, row-locked with SKIP LOCKED so two purges never share a row."""
        ...

    async def delete_attachments(self, attachment_ids: Sequence[UUID]) -> int: ...


class AdministratorDirectory(Protocol):
    async def active_administrator_ids(self) -> list[UUID]: ...


class WishlistStore(Protocol):
    async def add(self, *, user_id: UUID, product_id: UUID) -> bool:
        """True if this call inserted a new active row; False if one already
        existed. Never reactivates a soft-deleted row (VS-038 plan §3)."""
        ...

    async def remove(self, *, user_id: UUID, product_id: UUID) -> bool:
        """True if an active row was soft-deleted; False if there was none."""
        ...

    async def list_page(
        self, *, user_id: UUID, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[WishlistItem]: ...

    async def count_active(self) -> int: ...


class WishlistCounter(Protocol):
    async def adjust(self, product_id: UUID, delta: int) -> None:
        """`delta` is +1 or -1, from a caller that already confirmed a real
        state change on `wishlist_items`. Framework-free port so the
        application layer can call it without importing a session
        (VS-038 plan §3 refactor) - the adapter binds it to one."""
        ...
