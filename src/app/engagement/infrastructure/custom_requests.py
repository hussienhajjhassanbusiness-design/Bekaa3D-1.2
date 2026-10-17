from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, delete, func, insert, literal, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.application.ports import CustomRequestFunnel
from app.engagement.domain.custom_request import (
    QUOTE_CURRENCY,
    CustomRequest,
    CustomRequestAttachment,
    CustomRequestDetails,
    NewAttachment,
    PipelineChange,
)
from app.engagement.domain.enums import CustomRequestOutcome, CustomRequestStatus, UploadScanStatus
from app.engagement.infrastructure.models import CustomRequestAttachmentModel, CustomRequestModel

_R = CustomRequestModel
_REQUEST_COLUMNS = (
    _R.id,
    _R.name,
    _R.email,
    _R.phone,
    _R.project_title,
    _R.description,
    _R.preferred_material,
    _R.preferred_colour,
    _R.dimensions,
    _R.status,
    _R.quoted_amount_cents,
    _R.currency,
    _R.outcome,
    _R.admin_notes,
    _R.contacted_at,
    _R.quoted_at,
    _R.completed_at,
    _R.closed_at,
    _R.created_at,
    _R.updated_at,
)
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


def _request(row: Any, attachments: Sequence[CustomRequestAttachment]) -> CustomRequest:
    return CustomRequest(**row._mapping, attachments=tuple(attachments))


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
        inserted = (
            await self._session.execute(
                insert(_R)
                .values(
                    **vars(details),
                    status=CustomRequestStatus.NEW,
                    created_at=submitted_at,
                    updated_at=submitted_at,
                )
                .returning(*_REQUEST_COLUMNS)
            )
        ).one()
        rows: list[Any] = []
        if attachments:
            stmt = insert(_A).returning(*_ATTACHMENT_COLUMNS, sort_by_parameter_order=True)
            values = [
                {
                    **vars(a),
                    "custom_request_id": inserted.id,
                    "scan_status": UploadScanStatus.CLEAN,
                    "expires_at": expires_at,
                    "created_at": submitted_at,
                }
                for a in attachments
            ]
            rows = list((await self._session.execute(stmt, values)).all())
        return _request(inserted, [_attachment(row) for row in rows])

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


class SqlCustomRequestPipelineRepository:
    """Admin reads and pipeline writes (VS-035); writes run under `get_for_update`'s lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _with_attachments(self, rows: Sequence[Any], now: datetime) -> list[CustomRequest]:
        by_request: dict[UUID, list[CustomRequestAttachment]] = defaultdict(list)
        if rows:
            stmt = (
                select(*_ATTACHMENT_COLUMNS)
                .where(_A.custom_request_id.in_([row.id for row in rows]), _A.expires_at > now)
                .order_by(_A.created_at, _A.id)
            )
            for row in (await self._session.execute(stmt)).all():
                by_request[row.custom_request_id].append(_attachment(row))
        return [_request(row, by_request[row.id]) for row in rows]

    async def _one(self, stmt: Any, now: datetime) -> CustomRequest | None:
        row = (await self._session.execute(stmt)).first()
        return (await self._with_attachments([row], now))[0] if row is not None else None

    async def get(self, request_id: UUID, *, now: datetime) -> CustomRequest | None:
        return await self._one(select(*_REQUEST_COLUMNS).where(_R.id == request_id), now)

    async def get_for_update(self, request_id: UUID, *, now: datetime) -> CustomRequest | None:
        stmt = select(*_REQUEST_COLUMNS).where(_R.id == request_id).with_for_update()
        return await self._one(stmt, now)

    async def _update(
        self, request_id: UUID, values: dict[str, Any], now: datetime
    ) -> CustomRequest:
        stmt = (
            update(_R)
            .where(_R.id == request_id)
            .values(**values, updated_at=now)
            .returning(*_REQUEST_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        row = (await self._session.execute(stmt)).one()
        return (await self._with_attachments([row], now))[0]

    async def apply(
        self, request_id: UUID, change: PipelineChange, *, now: datetime
    ) -> CustomRequest:
        values: dict[str, Any] = {"status": change.status}
        if change.stamp is not None:
            values[change.stamp] = now
        if change.outcome is not None:
            values["outcome"] = change.outcome
        if change.quoted_amount_cents is not None:
            values["quoted_amount_cents"] = change.quoted_amount_cents
            values["currency"] = QUOTE_CURRENCY
        return await self._update(request_id, values, now)

    async def set_admin_notes(
        self, request_id: UUID, notes: str | None, *, now: datetime
    ) -> CustomRequest:
        return await self._update(request_id, {"admin_notes": notes}, now)

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[CustomRequestStatus, datetime, UUID] | None,
        status: CustomRequestStatus | None,
        created_after: datetime | None,
        created_before: datetime | None,
        email: str | None,
        now: datetime,
    ) -> list[CustomRequest]:
        """Queue order (status, created_at, id): actionable first, oldest first."""
        stmt = select(*_REQUEST_COLUMNS)
        if status is not None:
            stmt = stmt.where(_R.status == status)
        if created_after is not None:
            stmt = stmt.where(_R.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(_R.created_at < created_before)
        if email is not None:
            stmt = stmt.where(_R.email == email)
        if after is not None:
            after_status, after_created_at, after_id = after
            stmt = stmt.where(
                tuple_(_R.status, _R.created_at, _R.id)
                > tuple_(
                    literal(after_status, _R.status.type),
                    literal(after_created_at, DateTime(timezone=True)),
                    literal(after_id, postgresql.UUID(as_uuid=True)),
                )
            )
        stmt = stmt.order_by(_R.status, _R.created_at, _R.id).limit(limit)
        return await self._with_attachments((await self._session.execute(stmt)).all(), now)

    async def get_attachment(
        self, request_id: UUID, attachment_id: UUID
    ) -> CustomRequestAttachment | None:
        stmt = select(*_ATTACHMENT_COLUMNS).where(
            _A.id == attachment_id, _A.custom_request_id == request_id
        )
        row = (await self._session.execute(stmt)).first()
        return _attachment(row) if row is not None else None

    async def funnel(self, *, created_from: datetime, created_to: datetime) -> CustomRequestFunnel:
        won = _R.outcome == CustomRequestOutcome.WON
        stmt = select(
            func.count(),
            func.count(_R.contacted_at),
            func.count(_R.quoted_at),
            func.count().filter(won),
            func.count().filter(_R.outcome == CustomRequestOutcome.LOST),
            func.coalesce(func.sum(_R.quoted_amount_cents).filter(_R.quoted_at.is_not(None)), 0),
            func.coalesce(func.sum(_R.quoted_amount_cents).filter(won), 0),
        ).where(_R.created_at >= created_from, _R.created_at < created_to)
        row = (await self._session.execute(stmt)).one()
        return CustomRequestFunnel(*(int(value) for value in row))
