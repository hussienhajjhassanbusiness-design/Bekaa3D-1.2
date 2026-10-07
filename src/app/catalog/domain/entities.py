from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

# The three lifecycle states, and why there are three rather than two
# (`database-design.md` 6.1-6.3 gives both columns; this is the V1 reading of
# how they combine):
#
#   deleted_at IS NULL  AND is_active        -> live, shown publicly
#   deleted_at IS NULL  AND NOT is_active    -> disabled: retained, visible to
#                                               administrators, hidden publicly,
#                                               and reactivatable via PATCH
#   deleted_at IS NOT NULL                   -> archived: admin-readable,
#                                               publicly invisible, terminal in
#                                               V1 (there is no restore
#                                               endpoint), and its slug is
#                                               released for reuse
#
# Keeping "disabled" distinct from "archived" is what lets an administrator take
# a category off the storefront temporarily without burning its slug.


@dataclass
class _ReferenceValue:
    """Shared lifecycle for the three reference-data tables.

    They differ only in whether they carry a slug, so the state machine lives
    once here rather than being written out three times and drifting.
    """

    id: UUID
    name: str
    is_active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_archived(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_publicly_visible(self) -> bool:
        """What the public list endpoints are allowed to return.

        Expressed here as well as in the query predicate deliberately: the query
        is the thing that actually enforces it, and this is what the tests read
        so that a leak shows up as a disagreement between the two rather than as
        two copies of the same mistake.
        """
        return self.deleted_at is None and self.is_active

    def audit_snapshot(self) -> dict[str, Any]:
        """The before/after payload written to the audit log.

        Reference data carries no PII, so the whole row is recorded rather than
        a redacted subset - an auditor reading the row needs no join back to a
        table that may have changed again since.

        Lives in the domain rather than beside the API schemas: the application
        layer writes these rows, and it must not reach outward into `api` to do
        it.
        """
        return {
            "name": self.name,
            "is_active": self.is_active,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def archive(self, at: datetime) -> None:
        """Soft-delete. Sets both columns in one step.

        `is_active` is cleared alongside `deleted_at` so the row cannot sit in
        the contradictory "archived but still flagged active" state - every
        public query filters on both, and a row that satisfied one but not the
        other would be a latent bug waiting for a query that checks only one.
        """
        self.deleted_at = at
        self.is_active = False
        self.updated_at = at


@dataclass
class Category(_ReferenceValue):
    """A product grouping. V1 has no hierarchy - there is no `parent_id`."""

    slug: str

    def audit_snapshot(self) -> dict[str, Any]:
        """Adds the slug. Overridden rather than branched on `isinstance`, so a
        future reference type cannot be silently forgotten."""
        return {**super().audit_snapshot(), "slug": self.slug}

    def apply_update(
        self,
        *,
        name: str | None,
        slug: str | None,
        is_active: bool | None,
        at: datetime,
    ) -> bool:
        """Apply a partial update. Returns whether anything actually changed.

        Following `Setting.change_value`: a PATCH submitting the values already
        stored is a successful request that changes nothing, and the caller uses
        this answer to decide whether to touch `updated_at`. It is audited
        either way.
        """
        changed = False
        if name is not None and name != self.name:
            self.name = name
            changed = True
        if slug is not None and slug != self.slug:
            self.slug = slug
            changed = True
        if is_active is not None and is_active is not self.is_active:
            self.is_active = is_active
            changed = True
        if changed:
            self.updated_at = at
        return changed


@dataclass
class Material(_ReferenceValue):
    """A controlled material value. No slug - it is never addressed by URL."""

    def apply_update(self, *, name: str | None, is_active: bool | None, at: datetime) -> bool:
        changed = False
        if name is not None and name != self.name:
            self.name = name
            changed = True
        if is_active is not None and is_active is not self.is_active:
            self.is_active = is_active
            changed = True
        if changed:
            self.updated_at = at
        return changed


@dataclass
class Colour(_ReferenceValue):
    """A controlled colour value. Same shape as Material."""

    def apply_update(self, *, name: str | None, is_active: bool | None, at: datetime) -> bool:
        changed = False
        if name is not None and name != self.name:
            self.name = name
            changed = True
        if is_active is not None and is_active is not self.is_active:
            self.is_active = is_active
            changed = True
        if changed:
            self.updated_at = at
        return changed
