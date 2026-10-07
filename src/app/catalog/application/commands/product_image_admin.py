"""Administrator image writes (docs/product-images.md, ADR-021). Every command holds
the product's row lock while it reads and changes the gallery, so cover, order and
the image cap cannot race; each change is audited in the same transaction."""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.catalog.application.ports import ProductImageStore, ProductStore
from app.catalog.domain.exceptions import (
    MalwareDetectedError,
    ProductNotFoundError,
    UploadRejectedError,
)
from app.catalog.domain.product import ENTITY_TYPE as PRODUCT_ENTITY
from app.catalog.domain.product_image import ENTITY_TYPE, ProductGallery, ProductImage
from app.integrations.images.ports import ImageRejectedError, ImageSanitizerPort
from app.integrations.scanning.ports import MalwareScannerPort
from app.integrations.storage.ports import StoragePort
from app.platform.application.ports.audit_writer import AuditWriter

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
STORAGE_PREFIX = "products/"


class _ImageCommand:
    def __init__(
        self, products: ProductStore, images: ProductImageStore, audit: AuditWriter
    ) -> None:
        self._products = products
        self._images = images
        self._audit = audit

    async def _locked_gallery(self, product_id: UUID) -> ProductGallery:
        product = await self._products.get_for_update(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        product.ensure_live()
        return ProductGallery(await self._images.live_for_product(product_id))

    async def _record(
        self,
        action: str,
        entity: tuple[str, UUID],
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> None:
        await self._audit.record(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity[0],
            entity_id=entity[1],
            before_data=before,
            after_data=after,
            request_id=request_id,
            ip_hash=ip_hash,
        )


class UploadProductImage(_ImageCommand):
    def __init__(
        self,
        products: ProductStore,
        images: ProductImageStore,
        audit: AuditWriter,
        *,
        storage: StoragePort,
        scanner: MalwareScannerPort,
        sanitizer: ImageSanitizerPort,
    ) -> None:
        super().__init__(products, images, audit)
        self._storage = storage
        self._scanner = scanner
        self._sanitizer = sanitizer

    async def execute(
        self,
        *,
        product_id: UUID,
        data: bytes,
        alt_text: str | None,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ProductImage:
        """size -> scan the raw bytes -> sanitize -> lock and check -> store -> insert (ADR-021).
        The file is written before the row, so a failed commit leaves only an orphan
        file for `reap_orphan_files`, never a row pointing at a missing file (FR-04)."""
        product = await self._products.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        product.ensure_live()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise UploadRejectedError(f"an image must be 1 byte to {MAX_UPLOAD_BYTES} bytes")
        verdict = await self._scanner.scan(data)
        if not verdict.clean:
            raise MalwareDetectedError(verdict.signature)
        try:
            clean = await self._sanitizer.sanitize(data)
        except ImageRejectedError as exc:
            raise UploadRejectedError(exc.reason) from exc

        slot = (await self._locked_gallery(product_id)).next_slot()
        key = f"{STORAGE_PREFIX}{uuid.uuid4()}.{clean.extension}"
        await self._storage.put(key, clean.data)
        image = await self._images.add(
            product_id=product_id,
            storage_key=key,
            alt_text=alt_text,
            sort_order=slot.sort_order,
            is_cover=slot.is_cover,
        )
        await self._record(
            "product_image.uploaded",
            (ENTITY_TYPE, image.id),
            None,
            image.audit_snapshot(),
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return image


class UpdateProductImage(_ImageCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        image_id: UUID,
        alt_text: str | None,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ProductImage:
        """A no-op is still audited, with equal before and after (VS-007 convention)."""
        image = (await self._locked_gallery(product_id)).get(image_id)
        before = image.audit_snapshot()
        if image.alt_text != alt_text:
            image.alt_text, image.updated_at = alt_text, datetime.now(UTC)
            await self._images.save([image])
        await self._record(
            "product_image.updated",
            (ENTITY_TYPE, image.id),
            before,
            image.audit_snapshot(),
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return image


class SetProductCover(_ImageCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        image_id: UUID,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ProductImage:
        gallery = await self._locked_gallery(product_id)
        previous = next((i.id for i in gallery.images if i.is_cover), None)
        changed = gallery.set_cover(image_id, datetime.now(UTC))
        await self._images.save(changed)
        await self._record(
            "product_image.cover_set",
            (PRODUCT_ENTITY, product_id),
            {"cover_image_id": str(previous) if previous else None},
            {"cover_image_id": str(image_id)},
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return gallery.get(image_id)


class ReorderProductImages(_ImageCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        image_ids: list[UUID],
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> list[ProductImage]:
        gallery = await self._locked_gallery(product_id)
        before = [str(i.id) for i in gallery.images]
        await self._images.save(gallery.reorder(image_ids, datetime.now(UTC)))
        await self._record(
            "product_image.reordered",
            (PRODUCT_ENTITY, product_id),
            {"image_ids": before},
            {"image_ids": [str(i.id) for i in gallery.images]},
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return gallery.images


class DeleteProductImage(_ImageCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        image_id: UUID,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> None:
        """Soft delete; the file stays, since order snapshots may point at it (BR-033)."""
        gallery = await self._locked_gallery(product_id)
        before = gallery.get(image_id).audit_snapshot()
        image = gallery.delete(image_id, datetime.now(UTC))
        await self._images.save([image])
        await self._record(
            "product_image.deleted",
            (ENTITY_TYPE, image.id),
            before,
            image.audit_snapshot(),
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
