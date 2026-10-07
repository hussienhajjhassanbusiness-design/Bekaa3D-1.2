"""Administrator product writes, each atomic with its audit row (docs/products.md).
Edits are optimistic (ADR-020): a stale `version` writes nothing. Referenced values
are share-locked so an archive cannot slip in between (FR-04)."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.catalog.application.ports import ProductStore, ReferenceLocks
from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import (
    ProductNotFoundError,
    ReferenceValueUnusableError,
    VersionConflictError,
)
from app.catalog.domain.product import (
    ENTITY_TYPE,
    REFERENCE_FIELDS,
    Product,
    ProductAttributes,
    ProductDraft,
)
from app.catalog.domain.slug import normalise_slug
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class ProductMutationResult:
    product: Product
    changed: bool


async def _lock_references(
    references: ReferenceLocks, attrs: ProductAttributes, names: list[str]
) -> None:
    for name in names:
        value_id = getattr(attrs, name)
        if value_id is not None and not await references.lock_live(name, value_id):
            raise ReferenceValueUnusableError(name, value_id)


class _ProductCommand:
    def __init__(
        self, products: ProductStore, references: ReferenceLocks, audit: AuditWriter
    ) -> None:
        self._products = products
        self._references = references
        self._audit = audit

    async def _load(self, product_id: UUID, expected_version: int) -> Product:
        product = await self._products.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        product.ensure_live()
        if product.version != expected_version:
            raise VersionConflictError(product_id, product.version)
        return product

    async def _save(self, product: Product, expected_version: int) -> Product:
        saved = await self._products.save_if_version(product, expected_version)
        if saved is None:
            current = await self._products.current_version(product.id)
            raise VersionConflictError(product.id, current or expected_version)
        return saved

    async def _record(
        self,
        action: str,
        product: Product,
        before: dict[str, Any] | None,
        *,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> None:
        await self._audit.record(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=ENTITY_TYPE,
            entity_id=product.id,
            before_data=before,
            after_data=product.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )


class CreateProduct(_ProductCommand):
    async def execute(
        self,
        *,
        product_type: ProductType,
        attributes: ProductAttributes,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> Product:
        """Slug uniqueness is left to the live-slug index, never pre-checked."""
        attrs = replace(attributes, slug=normalise_slug(attributes.slug))
        draft = ProductDraft(product_type, attrs)
        await _lock_references(self._references, attrs, list(REFERENCE_FIELDS))
        product = await self._products.add(draft)
        await self._record(
            "product.created",
            product,
            None,
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return product


class UpdateProduct(_ProductCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        expected_version: int,
        changes: dict[str, Any],
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ProductMutationResult:
        """A no-op PATCH bumps nothing but is still audited (VS-007 convention)."""
        product = await self._load(product_id, expected_version)
        if changes.get("slug") is not None:
            changes = {**changes, "slug": normalise_slug(changes["slug"])}
        before = product.audit_snapshot()
        old = product.attributes
        changed = product.apply_update(changes, datetime.now(UTC))
        if changed:
            moved = [
                n for n in REFERENCE_FIELDS if getattr(product.attributes, n) != getattr(old, n)
            ]
            await _lock_references(self._references, product.attributes, moved)
            product = await self._save(product, expected_version)
        await self._record(
            "product.updated",
            product,
            before,
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return ProductMutationResult(product=product, changed=changed)


class DeleteProduct(_ProductCommand):
    async def execute(
        self,
        *,
        product_id: UUID,
        expected_version: int,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> Product:
        """Soft delete; the partial index releases the slug in the same transaction."""
        product = await self._load(product_id, expected_version)
        before = product.audit_snapshot()
        product.delete(datetime.now(UTC))
        product = await self._save(product, expected_version)
        await self._record(
            "product.deleted",
            product,
            before,
            actor_user_id=actor_user_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return product
