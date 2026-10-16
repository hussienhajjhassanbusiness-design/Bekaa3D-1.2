from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.catalog.application.ports import Product, ProductType
from app.engagement.domain.entities import Notification, WishlistItem
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


class WishlistItemRead(BaseModel):
    """One saved product. `available` is False when the product has since
    been soft-deleted or hidden (`is_visible = false`) - the row stays in the
    list rather than disappearing (VS-038 plan §10 Q6), reduced to `name` only.
    """

    product_id: UUID
    created_at: datetime
    available: bool
    name: str
    slug: str | None = None
    price_cents: int | None = None
    currency: str | None = None
    type: ProductType | None = None

    @classmethod
    def of(cls, item: WishlistItem, product: Product | None) -> "WishlistItemRead":
        if product is None:
            # Defensive only: BR-018 guarantees products are never hard-deleted,
            # so `ProductStore.get_many` always returns a row for a known id.
            return cls(
                product_id=item.product_id, created_at=item.created_at, available=False, name=""
            )
        available = not product.is_deleted and product.attributes.is_visible
        return cls(
            product_id=item.product_id,
            created_at=item.created_at,
            available=available,
            name=product.attributes.name,
            slug=product.attributes.slug if available else None,
            price_cents=product.attributes.price_cents if available else None,
            currency=product.attributes.currency if available else None,
            type=product.type if available else None,
        )


class WishlistPage(BaseModel):
    items: list[WishlistItemRead]
    next_cursor: str | None


class WishlistAnalyticsItem(BaseModel):
    product_id: UUID
    name: str
    slug: str
    wishlist_count: int


class WishlistAnalytics(BaseModel):
    total_active: int
    most_wishlisted: list[WishlistAnalyticsItem]
