from enum import StrEnum


class NotificationType(StrEnum):
    """The high-level category of an in-app notification (`notification_type`).

    Exactly the six values database-design.md 12.3 defines, and deliberately no
    more. The design is explicit that this enum stays a *stable high-level
    category* while "the specific event is carried in the JSON payload" - so a
    new business event does not need a migration, only a new `payload.event`
    value from the slice that emits it.

    Adding a value here is a migration in its own right (PostgreSQL enums are
    schema objects), which is exactly the friction the split is meant to create.
    """

    ACCOUNT = "account"
    ORDER = "order"
    PAYMENT = "payment"
    REFUND = "refund"
    OFFER = "offer"
    DOWNLOAD = "download"
