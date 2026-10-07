"""Reading settings from other bounded contexts.

Ordering, Engagement and the background jobs all need setting values, and none
of them may query the `settings` table directly - cross-context access goes
through a service interface, which is what keeps this a modular monolith rather
than a shared database (CLAUDE.md, architecture rules).

The reader works on a `SettingStore` bound to the caller's session rather than
opening its own (other contexts build one with `app.platform.public.settings_reader`).
That matters for correctness, not tidiness: FR-18 requires checkout to "recheck the
accepting-orders setting inside its transaction", which is only meaningful if
the read happens on the same connection and therefore the same snapshot as the
work it guards.
"""

from uuid import UUID

from app.platform.application.ports import SettingStore
from app.platform.domain.enums import SettingType
from app.platform.domain.exceptions import (
    SettingNotFoundError,
    SettingTypeMismatchError,
)
from app.platform.domain.settings_registry import (
    SettingValue,
    definition_for,
    validate_value,
)


class SettingsReader:
    """Validated reads of seeded settings, for internal consumers."""

    def __init__(self, settings: SettingStore) -> None:
        self._settings = settings

    async def get(self, key: str) -> SettingValue:
        """The current value of a registered setting.

        Validated on the way out, not only on the way in. The write path already
        checks every value, so a stored value that fails validation means the
        row was changed by something other than this application - a hand-edited
        database, a bad restore, a migration that seeded the wrong shape. The
        honest response to that is to fail where it is noticed rather than hand
        a consumer a value the system considers illegal.

        Raises `SettingNotFoundError` if the key is unregistered *or* its seeded
        row is missing, `SettingTypeMismatchError` if the stored type disagrees
        with the registry, and `InvalidSettingValueError` if the stored value
        does not satisfy its own rules.
        """
        definition = definition_for(key)
        setting = await self._settings.get_by_key(key)
        if setting is None:
            # Registered but absent: the seed migration should have created it,
            # so this is a deployment fault, not a caller error.
            raise SettingNotFoundError(key)
        if setting.type is not definition.type:
            raise SettingTypeMismatchError(key, setting.type, definition.type)
        return validate_value(key, setting.value)

    async def get_duration_seconds(self, key: str) -> int:
        """A `duration` setting as whole seconds.

        Durations are stored as integer seconds so arithmetic never depends on
        a unit the caller has to remember; `timedelta(seconds=...)` at the call
        site is then unambiguous.
        """
        definition = definition_for(key)
        if definition.type is not SettingType.DURATION:
            raise SettingTypeMismatchError(key, definition.type, SettingType.DURATION)
        value = await self.get(key)
        if type(value) is not int:
            raise SettingTypeMismatchError(key, type(value).__name__, "int")
        return value

    async def get_int(self, key: str) -> int:
        definition = definition_for(key)
        if definition.type is not SettingType.INTEGER:
            raise SettingTypeMismatchError(key, definition.type, SettingType.INTEGER)
        value = await self.get(key)
        if type(value) is not int:
            raise SettingTypeMismatchError(key, type(value).__name__, "int")
        return value

    async def get_bool(self, key: str) -> bool:
        definition = definition_for(key)
        if definition.type is not SettingType.BOOLEAN:
            raise SettingTypeMismatchError(key, definition.type, SettingType.BOOLEAN)
        value = await self.get(key)
        if type(value) is not bool:
            raise SettingTypeMismatchError(key, type(value).__name__, "bool")
        return value

    async def updated_by(self, key: str) -> UUID | None:
        setting = await self._settings.get_by_key(key)
        return setting.updated_by if setting else None
