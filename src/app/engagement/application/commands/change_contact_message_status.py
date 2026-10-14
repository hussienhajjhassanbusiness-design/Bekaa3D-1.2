from uuid import UUID

from app.engagement.application.ports import ContactMessageStore
from app.engagement.domain.contact_message import ContactMessage, check_transition
from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.domain.exceptions import ContactMessageNotFoundError
from app.platform.application.ports.audit_writer import AuditWriter

ENTITY_TYPE = "contact_message"


class ChangeContactMessageStatus:
    def __init__(self, messages: ContactMessageStore, audit: AuditWriter) -> None:
        self._messages = messages
        self._audit = audit

    async def execute(
        self,
        *,
        message_id: UUID,
        status: ContactMessageStatus,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> ContactMessage:
        """Checked against the locked row, so concurrent admins see each other (FR-16)."""
        message = await self._messages.get_for_update(message_id)
        if message is None:
            raise ContactMessageNotFoundError(message_id)
        before = message.status
        check_transition(before, status)
        if status != before:
            message = await self._messages.set_status(message_id, status)
        # Status only: name, email and body are PII and audit rows are permanent.
        await self._audit.record(
            actor_user_id=actor_user_id,
            action="contact_message.status_changed",
            entity_type=ENTITY_TYPE,
            entity_id=message_id,
            before_data={"status": before.value},
            after_data={"status": message.status.value},
            request_id=request_id,
            ip_hash=ip_hash,
        )
        return message
