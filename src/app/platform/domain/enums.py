from enum import StrEnum


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class SettingType(StrEnum):
    """The declared type of a setting's value (database-design.md `setting_type`).

    Fixed by the frozen schema, not by this slice - all six exist even though V1
    seeds no `json` setting, because the enum is part of the approved design and
    adding a value to a PostgreSQL enum later is a migration in its own right.

    `duration` is stored as whole seconds and `money` as the API's standard
    `{amount_cents, currency}` object; both are `integer` underneath but carry
    their own type so an admin UI can render the right editor and so validation
    can apply unit-specific rules."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    STRING = "string"
    MONEY = "money"
    DURATION = "duration"
    JSON = "json"
