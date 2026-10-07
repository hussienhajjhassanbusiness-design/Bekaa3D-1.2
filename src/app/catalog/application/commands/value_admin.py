"""Administrator operations on materials and colours, written once for both.
Same locking as `category_admin`; names are unique by index, never pre-checked;
archiving refuses a value a live product uses (`CATEGORY_IN_USE`, VS-013)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.exceptions import (
    ArchivedValueNotMutableError,
    ReferenceValueInUseError,
    ReferenceValueNotFoundError,
)
from app.platform.application.ports.audit_writer import AuditWriter

# PEP 695 type parameters, constrained to the two concrete reference types. The
# constraint (rather than a bound) is deliberate: it means each command is
# checked once against Material and once against Colour, so a method that only
# happened to exist on one of them would be caught.


class _ValueRepository[ValueT: (Material, Colour)](Protocol):
    async def add(self, *, name: str, is_active: bool) -> ValueT: ...

    async def get_by_id_for_update(self, value_id: UUID) -> ValueT | None: ...

    async def save(self, value: ValueT) -> None: ...

    async def is_in_use(self, value_id: UUID) -> bool: ...


@dataclass(frozen=True)
class ValueMutationResult[ValueT: (Material, Colour)]:
    value: ValueT
    # Whether anything actually moved. The route does not use it, but the tests
    # do, and it makes the no-op path explicit rather than something inferred
    # from timestamps.
    changed: bool


class CreateReferenceValue[ValueT: (Material, Colour)]:
    """`entity_type` is the audit `entity_type` ("Material"/"Colour"); the audit
    action is derived from it, so the two can never disagree."""

    def __init__(
        self,
        values: _ValueRepository[ValueT],
        audit: AuditWriter,
        *,
        entity_type: str,
    ) -> None:
        self._values: _ValueRepository[ValueT] = values
        self._audit = audit
        self._entity_type = entity_type

    async def execute(
        self,
        *,
        name: str,
        is_active: bool,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ValueT:
        """Insert, then audit - in that order and in one transaction, so a
        failed insert leaves no audit row claiming the value was created.

        No row lock: there is no existing row to lock.
        """
        value = await self._values.add(name=name, is_active=is_active)
        await self._audit.record(
            actor_user_id=actor_user_id,
            action=f"{self._entity_type.lower()}.created",
            entity_type=self._entity_type,
            entity_id=value.id,
            before_data=None,
            after_data=value.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return value


class UpdateReferenceValue[ValueT: (Material, Colour)]:
    def __init__(
        self,
        values: _ValueRepository[ValueT],
        audit: AuditWriter,
        *,
        entity_type: str,
    ) -> None:
        self._values: _ValueRepository[ValueT] = values
        self._audit = audit
        self._entity_type = entity_type

    async def execute(
        self,
        *,
        value_id: UUID,
        name: str | None,
        is_active: bool | None,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ValueMutationResult[ValueT]:
        """Partial update. Reactivating a disabled (not archived) row happens
        here, via `is_active=True`."""
        # Locked read first: the archived check, the audit "before" and the save
        # all have to act on the row as it is now.
        value = await self._values.get_by_id_for_update(value_id)
        if value is None:
            raise ReferenceValueNotFoundError(self._entity_type, value_id)
        if value.is_archived:
            raise ArchivedValueNotMutableError(self._entity_type, value_id)

        before = value.audit_snapshot()
        changed = value.apply_update(name=name, is_active=is_active, at=datetime.now(UTC))
        if changed:
            await self._values.save(value)

        # Audited whether or not anything moved, following the VS-007
        # convention: a PATCH submitting the values already stored is still an
        # administrator action on a protected resource, and the row then shows
        # equal before/after, which is an accurate description of what happened.
        await self._audit.record(
            actor_user_id=actor_user_id,
            action=f"{self._entity_type.lower()}.updated",
            entity_type=self._entity_type,
            entity_id=value.id,
            before_data=before,
            after_data=value.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return ValueMutationResult(value=value, changed=changed)


class ArchiveReferenceValue[ValueT: (Material, Colour)]:
    def __init__(
        self,
        values: _ValueRepository[ValueT],
        audit: AuditWriter,
        *,
        entity_type: str,
    ) -> None:
        self._values: _ValueRepository[ValueT] = values
        self._audit = audit
        self._entity_type = entity_type

    async def execute(
        self,
        *,
        value_id: UUID,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ValueT:
        """Soft-delete: sets `deleted_at` and clears `is_active` together."""
        value = await self._values.get_by_id_for_update(value_id)
        if value is None:
            raise ReferenceValueNotFoundError(self._entity_type, value_id)
        if value.is_archived:
            raise ArchivedValueNotMutableError(self._entity_type, value_id)
        if await self._values.is_in_use(value_id):
            raise ReferenceValueInUseError(self._entity_type, value_id)

        before = value.audit_snapshot()
        value.archive(datetime.now(UTC))
        await self._values.save(value)
        await self._audit.record(
            actor_user_id=actor_user_id,
            action=f"{self._entity_type.lower()}.archived",
            entity_type=self._entity_type,
            entity_id=value.id,
            before_data=before,
            after_data=value.audit_snapshot(),
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return value
