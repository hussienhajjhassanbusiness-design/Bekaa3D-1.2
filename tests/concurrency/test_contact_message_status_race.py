"""VS-033 / FR-16: two administrators moving one message at once must leave a true
audit chain. Without the row lock both read `new` and both succeed."""

import asyncio
import uuid
from contextlib import suppress

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.application.commands.change_contact_message_status import (
    ChangeContactMessageStatus,
)
from app.engagement.domain.contact_message import ContactMessage
from app.engagement.domain.enums import ContactMessageStatus
from app.engagement.domain.exceptions import InvalidContactMessageTransitionError
from app.engagement.infrastructure.contact_messages import SqlContactMessageRepository
from app.engagement.infrastructure.models import ContactMessageModel
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter
from tests.concurrency.barrier import meet_or_fail

# The locked loser waits inside PostgreSQL and cannot arrive; the winner moves on.
_AFTER_READ_TIMEOUT_SECONDS = 1.0


class _SyncedRepository(SqlContactMessageRepository):
    def __init__(
        self, session: AsyncSession, before_read: asyncio.Barrier, after_read: asyncio.Barrier
    ) -> None:
        super().__init__(session)
        self._before_read = before_read
        self._after_read = after_read

    async def _read(self, message: ContactMessage | None) -> ContactMessage | None:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._after_read.wait(), _AFTER_READ_TIMEOUT_SECONDS)
        return message

    async def get_for_update(self, message_id: uuid.UUID) -> ContactMessage | None:
        await meet_or_fail(self._before_read)
        return await self._read(await super().get_for_update(message_id))

    async def get(self, message_id: uuid.UUID) -> ContactMessage | None:
        await meet_or_fail(self._before_read)
        return await self._read(await super().get(message_id))


@pytest.mark.concurrency
@pytest.mark.integration
@pytest.mark.parametrize("run", range(3))
async def test_concurrent_status_changes_leave_a_true_audit_chain(
    db_engine: AsyncEngine, run: int
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        row = ContactMessageModel(name="Race", email=f"race-{run}@example.com", message="hi")
        db.add(row)
    message_id = row.id
    before_read, after_read = asyncio.Barrier(2), asyncio.Barrier(2)

    async def move(target: ContactMessageStatus) -> str:
        async with factory() as db, db.begin():
            command = ChangeContactMessageStatus(
                _SyncedRepository(db, before_read, after_read), SqlAuditWriter(db)
            )
            try:
                await command.execute(
                    message_id=message_id,
                    status=target,
                    actor_user_id=None,  # type: ignore[arg-type]
                    request_id=None,
                    ip_hash=None,
                )
            except InvalidContactMessageTransitionError:
                return "refused"
            return "moved"

    outcomes = await asyncio.gather(
        move(ContactMessageStatus.REPLIED), move(ContactMessageStatus.READ)
    )

    async with factory() as db:
        audits = (
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.entity_id == message_id,
                    AuditLogModel.action == "contact_message.status_changed",
                )
            )
        ).all()
        final = await db.scalar(
            select(ContactMessageModel.status).where(ContactMessageModel.id == message_id)
        )
    assert len(audits) == outcomes.count("moved")
    moves = [((a.before_data or {})["status"], (a.after_data or {})["status"]) for a in audits]
    starts = [before for before, _ in moves]
    assert starts.count("new") == 1, f"two writers both started from new: {starts}"
    chain = dict(moves)
    state = "new"
    while state in chain:
        state = chain.pop(state)
    assert not chain and state == final
