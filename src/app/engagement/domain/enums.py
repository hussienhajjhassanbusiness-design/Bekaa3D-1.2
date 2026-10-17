from enum import StrEnum


class NotificationType(StrEnum):
    """`notification_type`: database-design.md 12.3's six plus `custom_request` (ADR-030).
    A category, not an event: the event is `payload.event`, and a new category is DDL."""

    ACCOUNT = "account"
    ORDER = "order"
    PAYMENT = "payment"
    REFUND = "refund"
    OFFER = "offer"
    DOWNLOAD = "download"
    CUSTOM_REQUEST = "custom_request"


class ContactMessageStatus(StrEnum):
    """`contact_message_status`, database-design.md 3.12; declaration order is queue order."""

    NEW = "new"
    READ = "read"
    REPLIED = "replied"
    ARCHIVED = "archived"


class CustomRequestStatus(StrEnum):
    """`custom_request_status`, database-design.md 3.11 (SRS 20.7)."""

    NEW = "new"
    CONTACTED = "contacted"
    QUOTED = "quoted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    LOST = "lost"


class CustomRequestOutcome(StrEnum):
    WON = "won"
    LOST = "lost"


class UploadScanStatus(StrEnum):
    """Only `clean`: scanning is synchronous, so no other verdict is ever stored (ADR-030)."""

    CLEAN = "clean"
