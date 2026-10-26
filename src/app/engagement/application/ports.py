"""Engagement's repository ports. A pure `Protocol`: the application layer
depends on this, never on `app.engagement.infrastructure` (BUG-41)."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.catalog.application.ports import ReviewableProduct
from app.engagement.domain.contact_message import ContactDetails, ContactMessage, ProblemReport
from app.engagement.domain.custom_request import (
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    NewAttachment,
    PipelineChange,
)
from app.engagement.domain.entities import Notification, WishlistItem
from app.engagement.domain.enums import (
    ContactMessageStatus,
    CustomRequestStatus,
    NotificationType,
)
from app.engagement.domain.reviews import NewReview, Review


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

    async def add_problem_report(self, report: ProblemReport) -> ContactMessage: ...

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


@dataclass(frozen=True)
class CustomRequestFunnel:
    """One submission-date cohort; a stage counts every lead that ever reached it."""

    submitted: int
    contacted: int
    quoted: int
    won: int
    lost: int
    quoted_total_cents: int
    won_total_cents: int


class CustomRequestPipelineStore(Protocol):
    """The admin side of Bring Your Idea (VS-035); attachments listed are unexpired."""

    async def get(self, request_id: UUID, *, now: datetime) -> CustomRequest | None: ...

    async def get_for_update(self, request_id: UUID, *, now: datetime) -> CustomRequest | None: ...

    async def apply(
        self, request_id: UUID, change: PipelineChange, *, now: datetime
    ) -> CustomRequest: ...

    async def set_admin_notes(
        self, request_id: UUID, notes: str | None, *, now: datetime
    ) -> CustomRequest: ...

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[CustomRequestStatus, datetime, UUID] | None,
        status: CustomRequestStatus | None,
        created_after: datetime | None,
        created_before: datetime | None,
        email: str | None,
        now: datetime,
    ) -> list[CustomRequest]: ...

    async def get_attachment(
        self, request_id: UUID, attachment_id: UUID
    ) -> CustomRequestAttachment | None: ...

    async def funnel(self, *, created_from: datetime, created_to: datetime) -> CustomRequestFunnel:
        """Leads with `created_from <= created_at < created_to`."""
        ...


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


# Ordering's evidence read: of `product_ids`, those this user holds an earning line for.
PurchaseEvidence = Callable[[UUID, Sequence[UUID]], Awaitable[set[UUID]]]


class ReviewStore(Protocol):
    async def lock_user(self, user_id: UUID) -> None:
        """`R_user`: the per-user transaction advisory lock (VS-036 plan 3.2b)."""
        ...

    async def live_for(self, user_id: UUID, product_id: UUID) -> Review | None: ...

    async def own_product_id(self, review_id: UUID, user_id: UUID) -> UUID | None:
        """Unlocked; `product_id` is immutable, so it is safe to lock the product by it."""
        ...

    async def get_own_for_update(self, review_id: UUID, user_id: UUID) -> Review | None: ...

    async def insert(self, new: NewReview) -> Review:
        """`ReviewAlreadyExistsError` if the live unique index already holds one."""
        ...

    async def update(
        self, review_id: UUID, *, rating: int, body: str | None, verified: bool
    ) -> Review: ...

    async def soft_delete(self, review_id: UUID) -> None: ...

    async def visible_totals(self, product_id: UUID) -> tuple[int, int]:
        """(sum of ratings, count) over live, not hidden reviews."""
        ...


class ReviewTotals(Protocol):
    async def visible_totals(self, product_id: UUID) -> tuple[int, int]:
        """(sum of ratings, count) over live, not hidden reviews."""
        ...


class ReviewModerationStore(ReviewTotals, Protocol):
    """VS-037: the admin's hide / restore. Rows here include soft-deleted ones."""

    async def product_id_of(self, review_id: UUID) -> UUID | None:
        """Unlocked, any row; `product_id` is immutable, so the product lock can go first."""
        ...

    async def lock_for_moderation(self, review_id: UUID) -> Review | None:
        """`FOR UPDATE`, after the product lock (VS-037 plan 8.1)."""
        ...

    async def set_hidden(self, review_id: UUID, *, hidden: bool, at: datetime) -> None: ...


class ReviewableProducts(Protocol):
    async def lock(self, product_id: UUID) -> ReviewableProduct | None:
        """`FOR NO KEY UPDATE`: the aggregate writers' lock (plan 3.4)."""
        ...

    async def set_rating(self, product_id: UUID, average: Decimal, count: int) -> None: ...
