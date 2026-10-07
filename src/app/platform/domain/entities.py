from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.platform.domain.enums import OutboxStatus, SettingType
from app.platform.domain.settings_registry import SettingValue

MAX_OUTBOX_ATTEMPTS = 5

REDACTED = "[redacted]"


@dataclass
class EmailOutboxMessage:
    id: UUID
    user_id: UUID | None
    recipient_email: str
    template: str
    payload: dict[str, Any]
    status: OutboxStatus
    send_after: datetime
    attempt_count: int
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def _redact_payload(self) -> None:
        """Strip the payload's values once the row can no longer be delivered.

        The payload carries the *raw* verification token - it has to, the
        provider needs it to render the link. But `verification_tokens` stores
        only a SHA-256 hash precisely so a database leak yields nothing
        redeemable, and an outbox row retained "through operational/audit
        retention" (database-design.md 21) with the plaintext in it gives that
        guarantee straight back. Keys are kept so the row still shows what was
        sent; only the values go.
        """
        self.payload = dict.fromkeys(self.payload, REDACTED)

    def mark_sent(self, at: datetime) -> None:
        self.status = OutboxStatus.SENT
        self.sent_at = at
        self.updated_at = at
        self._redact_payload()

    def scrub(self, text: str) -> str:
        """`text` with every payload value replaced by REDACTED.

        A provider's exception often echoes the request it failed on (HTTP
        APIs typically put the body in the error), and the request carries the
        raw token. Payload redaction alone left that copy in `last_error` for
        good (BUG-22). Longest values first, so a value that contains another
        is replaced whole."""
        values = sorted(
            {str(value) for value in self.payload.values() if value not in (None, "")},
            key=len,
            reverse=True,
        )
        for value in values:
            text = text.replace(value, REDACTED)
        return text

    def mark_failed(self, error: str, *, next_attempt_at: datetime, at: datetime) -> None:
        self.attempt_count += 1
        # Scrubbed before truncation, so a value cut off at the 1000-character
        # boundary cannot survive half-redacted.
        self.last_error = self.scrub(error)[:1000]
        self.updated_at = at
        if self.attempt_count >= MAX_OUTBOX_ATTEMPTS:
            self.status = OutboxStatus.FAILED
            # Terminal too: nothing retries a failed row and there is no requeue
            # path, so its token is dead weight that only adds exposure.
            self._redact_payload()
        else:
            self.status = OutboxStatus.PENDING
            self.send_after = next_attempt_at


@dataclass
class AuditLogEntry:
    id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    request_id: str | None
    ip_hash: str | None
    created_at: datetime


@dataclass
class Setting:
    """One typed, administrator-editable business parameter.

    The entity deliberately holds no validation rules: what a value may be is
    declared once in `settings_registry`, and duplicating it here would create
    two places to change a limit. What lives here is the one piece of behaviour
    that is genuinely about this row - deciding whether a write is a change.
    """

    id: UUID
    key: str
    type: SettingType
    value: SettingValue
    description: str | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime

    def change_value(self, new_value: SettingValue, *, actor_id: UUID, at: datetime) -> bool:
        """Apply a validated value. Returns whether anything actually changed.

        A PATCH that submits the value already stored is a successful request
        that changes nothing, and the caller uses this answer to decide whether
        to touch `updated_at`/`updated_by`. It is still audited - FR-18 requires
        both of two concurrent attempts to be audited, and under last-commit
        semantics the second one frequently *is* a no-op.

        The type is compared as well as the value because Python treats
        `True == 1` as true. Validation makes that unreachable for a registered
        key, since a boolean setting rejects `1` and an integer setting rejects
        `true` - but a comparison that would silently call those equal is not
        one to leave sitting in an entity.
        """
        if type(self.value) is type(new_value) and self.value == new_value:
            return False
        self.value = new_value
        self.updated_by = actor_id
        self.updated_at = at
        return True
