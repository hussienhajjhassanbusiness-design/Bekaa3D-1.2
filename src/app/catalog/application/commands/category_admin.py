"""Administrator operations on categories, each atomic with its audit row.
Mutations lock the row first (docs/reference-data.md); archiving refuses a
category a live product uses (`CATEGORY_IN_USE`, VS-013)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.catalog.application.ports import CategoryStore
from app.catalog.domain.entities import Category
from app.catalog.domain.exceptions import (
    ArchivedValueNotMutableError,
    ReferenceValueInUseError,
    ReferenceValueNotFoundError,
)
from app.catalog.domain.slug import normalise_slug
from app.platform.application.ports.audit_writer import AuditWriter

ENTITY_TYPE = "Category"


@dataclass(frozen=True)
class CategoryMutationResult:
    category: Category
    # Whether anything actually moved. The route does not use it, but the tests
    # do, and it makes the no-op path explicit rather than something inferred
    # from timestamps.
    changed: bool


class CreateCategory:
    def __init__(self, categories: CategoryStore, audit: AuditWriter) -> None:
        self._categories = categories
        self._audit = audit

    async def execute(
        self,
        *,
        name: str,
        slug: str,
        is_active: bool,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> Category:
        """Insert, then audit - in that order and in one transaction.

        Ordering matters: the insert can fail on the live-slug unique index, and
        auditing afterwards means a rejected create leaves no audit row claiming
        a category was created. `get_session` wraps the request in a single
        transaction, so either both land or neither does.

        Uniqueness is *not* checked by reading first. A `SELECT` followed by an
        `INSERT` has a window between them in which another administrator can
        commit the same slug, and the read would report the slug free when it is
        about to not be. The partial unique index is the only authority; a
        violation is translated to `SlugConflictError` by the repository.
        """
        category = await self._categories.add(
            name=name, slug=normalise_slug(slug), is_active=is_active
        )
        await self._audit.record(
            actor_user_id=actor_user_id,
            action="category.created",
            entity_type=ENTITY_TYPE,
            entity_id=category.id,
            before_data=None,
            after_data=category.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return category


class UpdateCategory:
    def __init__(self, categories: CategoryStore, audit: AuditWriter) -> None:
        self._categories = categories
        self._audit = audit

    async def execute(
        self,
        *,
        category_id: UUID,
        name: str | None,
        slug: str | None,
        is_active: bool | None,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> CategoryMutationResult:
        """Partial update. Reactivating a disabled (not archived) row happens
        here, via `is_active=True`."""
        # Locked read first: everything below - the archived check, the audit
        # "before", and the save - has to act on the row as it is now, not as it
        # was before a concurrent transaction committed.
        category = await self._categories.get_by_id_for_update(category_id)
        if category is None:
            raise ReferenceValueNotFoundError(ENTITY_TYPE, category_id)
        if category.is_archived:
            # Archiving is terminal in V1 - there is no restore endpoint - so an
            # archived row is not editable through the ordinary PATCH. With the
            # lock held, a PATCH that lost the race to an archive sees the
            # committed archived state here and is correctly refused.
            raise ArchivedValueNotMutableError(ENTITY_TYPE, category_id)

        before = category.audit_snapshot()
        changed = category.apply_update(
            name=name,
            slug=normalise_slug(slug) if slug is not None else None,
            is_active=is_active,
            at=datetime.now(UTC),
        )
        if changed:
            await self._categories.save(category)

        # Audited whether or not anything moved, following the VS-007
        # convention: a PATCH submitting the values already stored is still an
        # administrator action on a protected resource, and the row then shows
        # equal before/after, which is an accurate description of what happened.
        await self._audit.record(
            actor_user_id=actor_user_id,
            action="category.updated",
            entity_type=ENTITY_TYPE,
            entity_id=category.id,
            before_data=before,
            after_data=category.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return CategoryMutationResult(category=category, changed=changed)


class ArchiveCategory:
    def __init__(self, categories: CategoryStore, audit: AuditWriter) -> None:
        self._categories = categories
        self._audit = audit

    async def execute(
        self,
        *,
        category_id: UUID,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> Category:
        """Soft-delete, releasing the slug. Holding the row lock while checking
        usage is what makes a racing product assignment lose (FR-04)."""
        category = await self._categories.get_by_id_for_update(category_id)
        if category is None:
            raise ReferenceValueNotFoundError(ENTITY_TYPE, category_id)
        if category.is_archived:
            raise ArchivedValueNotMutableError(ENTITY_TYPE, category_id)
        if await self._categories.is_in_use(category_id):
            raise ReferenceValueInUseError(ENTITY_TYPE, category_id)

        before = category.audit_snapshot()
        category.archive(datetime.now(UTC))
        await self._categories.save(category)
        await self._audit.record(
            actor_user_id=actor_user_id,
            action="category.archived",
            entity_type=ENTITY_TYPE,
            entity_id=category.id,
            before_data=before,
            after_data=category.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return category
