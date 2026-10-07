from typing import Any


class PlatformDomainError(Exception):
    """Base for platform-context domain errors. No HTTP knowledge lives here -
    routers translate these into the SRS-defined stable error codes."""


class SettingNotFoundError(PlatformDomainError):
    """No setting exists for this key.

    Raised for two different callers with two different meanings, and both are
    correct. For the admin API it means the caller named a key that is not in
    the registry - keys are schema-defined and cannot be created through the API
    (api-endpoints.md:632), so this is a 404. For an internal consumer reading a
    seeded key it means the row is missing from a database that should have been
    seeded by migration, which is a deployment fault and must fail loudly rather
    than fall back to a constant.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"No setting is registered under the key {key!r}.")
        self.key = key


class InvalidSettingValueError(PlatformDomainError):
    """A value does not satisfy its key's declared type or range.

    Carries the reasons as a list because one submitted value can fail more than
    one rule at once (a money object can have both a bad currency and a
    negative amount), and an admin fixing it should see all of them rather than
    discovering them one request at a time.
    """

    def __init__(self, key: str, reasons: list[str]) -> None:
        super().__init__(f"Value for setting {key!r} is invalid: {'; '.join(reasons)}")
        self.key = key
        self.reasons = reasons


class SettingTypeMismatchError(PlatformDomainError):
    """The stored row's declared type disagrees with the code registry.

    Only reachable if a migration seeded a type the registry does not declare,
    or the registry changed without a migration. Treated as a fault rather than
    reconciled silently: the two are meant to be one fact in two places, and
    quietly preferring either one would hide a real deployment problem.
    """

    def __init__(self, key: str, stored: Any, expected: Any) -> None:
        super().__init__(
            f"Setting {key!r} is stored as type {stored!r} but the registry declares {expected!r}."
        )
        self.key = key
        self.stored = stored
        self.expected = expected
