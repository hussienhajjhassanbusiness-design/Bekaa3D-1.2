from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.catalog.domain.exceptions import (
    CoverDeletionBlockedError,
    ImageOrderMismatchError,
    ProductImageNotFoundError,
    UploadRejectedError,
)

ENTITY_TYPE = "ProductImage"
MAX_IMAGES_PER_PRODUCT = 20
MAX_ALT_TEXT_LENGTH = 300


@dataclass
class ProductImage:
    id: UUID
    product_id: UUID
    storage_key: str
    alt_text: str | None
    sort_order: int
    is_cover: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    def audit_snapshot(self) -> dict[str, Any]:
        return {
            "product_id": str(self.product_id),
            "storage_key": self.storage_key,
            "alt_text": self.alt_text,
            "sort_order": self.sort_order,
            "is_cover": self.is_cover,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


@dataclass(frozen=True)
class NewImageSlot:
    sort_order: int
    is_cover: bool


class ProductGallery:
    """The live images of one product, read under its row lock (docs/product-images.md)."""

    def __init__(self, images: list[ProductImage]) -> None:
        self.images = sorted(images, key=lambda i: (i.sort_order, i.created_at, str(i.id)))

    def get(self, image_id: UUID) -> ProductImage:
        for image in self.images:
            if image.id == image_id:
                return image
        raise ProductImageNotFoundError(image_id)

    def next_slot(self) -> NewImageSlot:
        """The first live image becomes the cover (owner decision)."""
        if len(self.images) >= MAX_IMAGES_PER_PRODUCT:
            raise UploadRejectedError(f"a product holds at most {MAX_IMAGES_PER_PRODUCT} images")
        last = max((i.sort_order for i in self.images), default=-1)
        return NewImageSlot(sort_order=last + 1, is_cover=not self.images)

    def set_cover(self, image_id: UUID, at: datetime) -> list[ProductImage]:
        """Returns the changed images, the one losing the cover first."""
        target = self.get(image_id)
        if target.is_cover:
            return []
        changed = [i for i in self.images if i.is_cover]
        for image in changed:
            image.is_cover, image.updated_at = False, at
        target.is_cover, target.updated_at = True, at
        return [*changed, target]

    def reorder(self, image_ids: list[UUID], at: datetime) -> list[ProductImage]:
        live = {i.id for i in self.images}
        if len(image_ids) != len(set(image_ids)) or set(image_ids) != live:
            raise ImageOrderMismatchError("image_ids must list every live image exactly once")
        changed = []
        for position, image_id in enumerate(image_ids):
            image = self.get(image_id)
            if image.sort_order != position:
                image.sort_order, image.updated_at = position, at
                changed.append(image)
        self.images.sort(key=lambda i: i.sort_order)
        return changed

    def delete(self, image_id: UUID, at: datetime) -> ProductImage:
        """Soft delete; the cover may go only when it is the last live image."""
        image = self.get(image_id)
        if image.is_cover and len(self.images) > 1:
            raise CoverDeletionBlockedError(image_id)
        image.deleted_at, image.is_cover, image.updated_at = at, False, at
        self.images.remove(image)
        return image
