from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.domain.custom_request import (
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    NewAttachment,
)
from app.engagement.domain.enums import CustomRequestStatus, UploadScanStatus
from app.engagement.infrastructure.models import CustomRequestAttachmentModel, CustomRequestModel

_A = CustomRequestAttachmentModel
_ATTACHMENT_COLUMNS = (
    _A.id,
    _A.custom_request_id,
    _A.storage_key,
    _A.original_filename,
    _A.mime_type,
    _A.size_bytes,
    _A.checksum,
    _A.expires_at,
    _A.created_at,
)


def _attachment(row: Any) -> CustomRequestAttachment:
    return CustomRequestAttachment(**row._mapping)


class SqlCustomRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        details: CustomRequestDetails,
        attachments: Sequence[NewAttachment],
        *,
        submitted_at: datetime,
        expires_at: datetime,
    ) -> CustomRequest:
        """One clock for both timestamps, so `expires_at - created_at` is the retention."""
        inserted = await self._session.execute(
            insert(CustomRequestModel)
            .values(
                **vars(details),
                status=CustomRequestStatus.NEW,
                created_at=submitted_at,
                updated_at=submitted_at,
            )
            .returning(CustomRequestModel.id)
        )
        request_id: UUID = inserted.scalar_one()
        rows: list[Any] = []
        if attachments:
            stmt = insert(_A).returning(*_ATTACHMENT_COLUMNS, sort_by_parameter_order=True)
            values = [
                {
                    **vars(a),
                    "custom_request_id": request_id,
                    "scan_status": UploadScanStatus.CLEAN,
                    "expires_at": expires_at,
                    "created_at": submitted_at,
                }
                for a in attachments
            ]
            rows = list((await self._session.execute(stmt, values)).all())
        return CustomRequest(
            id=request_id,
            project_title=details.project_title,
            status=CustomRequestStatus.NEW,
            created_at=submitted_at,
            attachments=tuple(_attachment(row) for row in rows),
        )

    async def lock_expired_attachments(
        self, *, now: datetime, limit: int
    ) -> list[CustomRequestAttachment]:
        stmt = (
            select(*_ATTACHMENT_COLUMNS)
            .where(_A.expires_at <= now)
            .order_by(_A.expires_at, _A.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [_attachment(row) for row in (await self._session.execute(stmt)).all()]

    async def delete_attachments(self, attachment_ids: Sequence[UUID]) -> int:
        if not attachment_ids:
            return 0
        result = await self._session.execute(
            delete(_A).where(_A.id.in_(attachment_ids)).returning(_A.id)
        )
        return len(result.all())

    async def referenced_keys(self, keys: Sequence[str]) -> set[str]:
        """Which of `keys` a row still names; the reaper deletes the rest (SRS 23)."""
        if not keys:
            return set()
        stmt = select(_A.storage_key).where(_A.storage_key.in_(keys))
        return set((await self._session.scalars(stmt)).all())
