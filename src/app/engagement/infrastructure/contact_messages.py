from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, func, literal, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.domain.contact_message import ContactDetails, ContactMessage, ProblemReport
from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.infrastructure.models import ContactMessageModel

_M = ContactMessageModel
_COLUMNS = (
    _M.id,
    _M.name,
    _M.email,
    _M.phone,
    _M.subject,
    _M.message,
    _M.status,
    _M.created_at,
    _M.updated_at,
    _M.user_id,
    _M.order_id,
)


def _to_domain(row: Any) -> ContactMessage:
    return ContactMessage(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        subject=row.subject,
        message=row.message,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        user_id=row.user_id,
        order_id=row.order_id,
    )


class SqlContactMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, details: ContactDetails) -> ContactMessage:
        stmt = (
            postgresql.insert(_M)
            .values(
                name=details.name,
                email=details.email,
                phone=details.phone,
                subject=details.subject,
                message=details.message,
            )
            .returning(*_COLUMNS)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def add_problem_report(self, report: ProblemReport) -> ContactMessage:
        stmt = (
            postgresql.insert(_M)
            .values(
                name=report.name,
                email=report.email,
                subject=report.subject,
                message=report.message,
                user_id=report.user_id,
                order_id=report.order_id,
            )
            .returning(*_COLUMNS)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def get(self, message_id: UUID) -> ContactMessage | None:
        row = (await self._session.execute(select(*_COLUMNS).where(_M.id == message_id))).first()
        return _to_domain(row) if row is not None else None

    async def get_for_update(self, message_id: UUID) -> ContactMessage | None:
        stmt = select(*_COLUMNS).where(_M.id == message_id).with_for_update()
        row = (await self._session.execute(stmt)).first()
        return _to_domain(row) if row is not None else None

    async def set_status(self, message_id: UUID, status: ContactMessageStatus) -> ContactMessage:
        stmt = (
            update(_M)
            .where(_M.id == message_id)
            .values(status=status, updated_at=func.now())
            .returning(*_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[ContactMessageStatus, datetime, UUID] | None,
        status: ContactMessageStatus | None,
        created_after: datetime | None,
        created_before: datetime | None,
        email: str | None,
    ) -> list[ContactMessage]:
        """Queue order (status, created_at, id): new first, oldest first."""
        stmt = select(*_COLUMNS)
        if status is not None:
            stmt = stmt.where(_M.status == status)
        if created_after is not None:
            stmt = stmt.where(_M.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(_M.created_at < created_before)
        if email is not None:
            stmt = stmt.where(_M.email == email)
        if after is not None:
            after_status, after_created_at, after_id = after
            stmt = stmt.where(
                tuple_(_M.status, _M.created_at, _M.id)
                > tuple_(
                    literal(after_status, _M.status.type),
                    literal(after_created_at, DateTime(timezone=True)),
                    literal(after_id, postgresql.UUID(as_uuid=True)),
                )
            )
        stmt = stmt.order_by(_M.status, _M.created_at, _M.id).limit(limit)
        return [_to_domain(row) for row in (await self._session.execute(stmt)).all()]
