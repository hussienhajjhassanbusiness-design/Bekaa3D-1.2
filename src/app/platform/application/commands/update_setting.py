from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.platform.application.ports import AuditLog, SettingStore
from app.platform.domain.entities import Setting
from app.platform.domain.exceptions import SettingNotFoundError
from app.platform.domain.settings_registry import SettingValue, definition_for, validate_value


@dataclass(frozen=True)
class UpdateSettingResult:
    setting: Setting
    # Whether the stored value actually moved. The route does not use this, but
    # the tests do, and it makes the no-op path explicit rather than something
    # you have to infer from timestamps.
    changed: bool


class UpdateSetting:
    """Change one typed setting, atomically with its audit row.

    The concurrency requirement (FR-18) is that two administrators editing the
    same setting produce "deterministic conflict or last-commit behavior with
    both attempts audited". This implements last-commit, serialised on the row:

        SELECT ... FOR UPDATE  ->  validate  ->  capture current  ->  update
                               ->  audit     ->  commit

    Taking the lock *first* is what makes the audit trail honest. The second
    administrator blocks until the first commits, then re-reads and sees the
    first one's value as its own "before" - so a race produces `10 -> 20` then
    `20 -> 30`, not two rows both claiming they changed 10. Without the lock
    both would read 10 and the audit log would describe a history that never
    happened.

    Holding the lock across validation is deliberate and cheap: validation is
    pure in-memory type and range checking, microseconds, with no hashing or
    I/O. (Login had to move Argon2 *outside* its lock for exactly the opposite
    reason.)

    Optimistic locking with a version column and a 409 was the alternative the
    requirement also permits. It was rejected because it needs a column the
    frozen schema does not have and a conflict code the error catalogue does not
    define, to solve a contention problem that does not exist on a 12-row table
    edited by one or two administrators.
    """

    def __init__(
        self,
        settings_repo: SettingStore,
        audit_repo: AuditLog,
    ) -> None:
        self._settings = settings_repo
        self._audit = audit_repo

    async def execute(
        self,
        *,
        key: str,
        value: SettingValue,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> UpdateSettingResult:
        # Registry first, so an unregistered key is refused before any lock is
        # taken. Keys are schema-defined; the API can never create one.
        definition_for(key)

        setting = await self._settings.get_by_key_for_update(key)
        if setting is None:
            raise SettingNotFoundError(key)

        # Raises InvalidSettingValueError, which the route turns into
        # 422 SETTING_INVALID. Nothing has been written at this point, so the
        # transaction rolls back clean.
        validated = validate_value(key, value)

        # Captured from the locked row, so it is the value this update actually
        # replaced rather than whatever was read before waiting for the lock.
        before = setting.value

        now = datetime.now(UTC)
        changed = setting.change_value(validated, actor_id=actor_user_id, at=now)
        if changed:
            await self._settings.save(setting)

        # Audited whether or not the value moved. A no-op PATCH is still an
        # administrator action on a protected resource, and FR-18 asks for both
        # of two concurrent attempts to be recorded - under last-commit
        # semantics the loser frequently *is* a no-op. The row then shows equal
        # before/after, which is an accurate description of what happened.
        #
        # In the same transaction as the write above: `get_session` wraps the
        # request, so either both land or neither does. A committed setting with
        # no audit row would be exactly the gap BR-132 exists to close.
        await self._audit.add(
            actor_user_id=actor_user_id,
            action="setting.updated",
            entity_type="Setting",
            entity_id=setting.id,
            # The key travels in both halves so an audit row is readable on its
            # own, without joining back to a table whose row may since have
            # changed again.
            before_data={"key": key, "value": before},
            after_data={"key": key, "value": setting.value},
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return UpdateSettingResult(setting=setting, changed=changed)
