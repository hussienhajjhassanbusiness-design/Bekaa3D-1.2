"""The administrator's Bring Your Idea pipeline (VS-035, FR-15). Each write locks the row,
rechecks its state and records an audit row in the same transaction (FR-17)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from app.engagement.application.ports import CustomRequestPipelineStore
from app.engagement.domain.custom_request import (
    CustomRequest,
    CustomRequestAttachment,
    is_expired,
    plan_transition,
)
from app.engagement.domain.enums import CustomRequestStatus
from app.engagement.domain.exceptions import (
    CustomRequestAttachmentNotFoundError,
    CustomRequestNotFoundError,
)
from app.integrations.storage.ports import ObjectNotFoundError, ObjectStream, StoragePort
from app.platform.application.ports.audit_writer import AuditWriter

ENTITY_TYPE = "custom_request"
ATTACHMENT_ENTITY_TYPE = "custom_request_attachment"
logger = structlog.get_logger()


@dataclass(frozen=True)
class AdminContext:
    """Who acted, for the audit row."""

    actor_user_id: UUID
    request_id: str | None
    ip_hash: str | None


class TransitionCustomRequest:
    def __init__(self, requests: CustomRequestPipelineStore, audit: AuditWriter) -> None:
        self._requests = requests
        self._audit = audit

    async def execute(
        self,
        *,
        custom_request_id: UUID,
        target: CustomRequestStatus,
        quoted_amount_cents: int | None,
        now: datetime,
        context: AdminContext,
    ) -> CustomRequest:
        """Checked against the locked row, so of two racing admins one gets a 409."""
        lead = await self._requests.get_for_update(custom_request_id, now=now)
        if lead is None:
            raise CustomRequestNotFoundError(custom_request_id)
        before = lead.status
        change = plan_transition(before, target, quoted_amount_cents)
        lead = await self._requests.apply(custom_request_id, change, now=now)
        # Pipeline fields only: the visitor's details are PII and audit rows are permanent.
        await self._audit.record(
            actor_user_id=context.actor_user_id,
            action="custom_request.transitioned",
            entity_type=ENTITY_TYPE,
            entity_id=custom_request_id,
            before_data={"status": before.value},
            after_data={
                "status": lead.status.value,
                "outcome": lead.outcome.value if lead.outcome else None,
                "quoted_amount_cents": lead.quoted_amount_cents,
                "currency": lead.currency,
            },
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )
        return lead


class UpdateCustomRequestNotes:
    def __init__(self, requests: CustomRequestPipelineStore, audit: AuditWriter) -> None:
        self._requests = requests
        self._audit = audit

    async def execute(
        self,
        *,
        custom_request_id: UUID,
        admin_notes: str | None,
        now: datetime,
        context: AdminContext,
    ) -> CustomRequest:
        lead = await self._requests.get_for_update(custom_request_id, now=now)
        if lead is None:
            raise CustomRequestNotFoundError(custom_request_id)
        had_notes = lead.admin_notes is not None
        lead = await self._requests.set_admin_notes(custom_request_id, admin_notes, now=now)
        # Never the text: notes may quote the visitor, and audit rows are permanent.
        await self._audit.record(
            actor_user_id=context.actor_user_id,
            action="custom_request.notes_updated",
            entity_type=ENTITY_TYPE,
            entity_id=custom_request_id,
            before_data={"has_notes": had_notes},
            after_data={"has_notes": lead.admin_notes is not None},
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )
        return lead


class OpenCustomRequestAttachment:
    def __init__(
        self, requests: CustomRequestPipelineStore, storage: StoragePort, audit: AuditWriter
    ) -> None:
        self._requests = requests
        self._storage = storage
        self._audit = audit

    async def execute(
        self,
        *,
        custom_request_id: UUID,
        attachment_id: UUID,
        now: datetime,
        context: AdminContext,
    ) -> tuple[CustomRequestAttachment, ObjectStream]:
        """Expired counts as gone even before the purge runs (VS-035, BR-115)."""
        attachment = await self._requests.get_attachment(custom_request_id, attachment_id)
        if attachment is None or is_expired(attachment, now):
            raise CustomRequestAttachmentNotFoundError(attachment_id)
        try:
            stream = await self._storage.open(attachment.storage_key)
        except ObjectNotFoundError as exc:
            await logger.awarning(
                "custom_request_attachment_file_missing", attachment_id=str(attachment_id)
            )
            raise CustomRequestAttachmentNotFoundError(attachment_id) from exc
        await self._audit.record(
            actor_user_id=context.actor_user_id,
            action="custom_request_attachment.downloaded",
            entity_type=ATTACHMENT_ENTITY_TYPE,
            entity_id=attachment_id,
            after_data={"custom_request_id": str(custom_request_id)},
            request_id=context.request_id,
            ip_hash=context.ip_hash,
        )
        return attachment, stream
