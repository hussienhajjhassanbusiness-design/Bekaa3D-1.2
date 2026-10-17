"""VS-035 / FR-15: conflicting administrator transitions from one state must not both commit.
Without the row lock both racers read `contacted` and both succeed."""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.application.commands.custom_request_pipeline import (
    AdminContext,
    TransitionCustomRequest,
)
from app.engagement.domain.custom_request import CustomRequest
from app.engagement.domain.enums import CustomRequestStatus
from app.engagement.domain.exceptions import InvalidCustomRequestTransitionError
from app.engagement.infrastructure.custom_requests import SqlCustomRequestPipelineRepository
from app.engagement.infrastructure.models import CustomRequestModel
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter
from tests.concurrency.barrier import meet_or_fail

# The locked loser waits inside PostgreSQL and cannot arrive; the winner moves on.
_AFTER_READ_TIMEOUT_SECONDS = 1.0
S = CustomRequestStatus


class _SyncedRepository(SqlCustomRequestPipelineRepository):
    def __init__(
        self, session: AsyncSession, before_read: asyncio.Barrier, after_read: asyncio.Barrier
    ) -> None:
        super().__init__(session)
        self._before_read = before_read
        self._after_read = after_read

    async def _read(self, lead: CustomRequest | None) -> CustomRequest | None:
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._after_read.wait(), _AFTER_READ_TIMEOUT_SECONDS)
        return lead

    async def get_for_update(self, request_id: uuid.UUID, *, now: datetime) -> CustomRequest | None:
        await meet_or_fail(self._before_read)
        return await self._read(await super().get_for_update(request_id, now=now))

    async def get(self, request_id: uuid.UUID, *, now: datetime) -> CustomRequest | None:
        await meet_or_fail(self._before_read)
        return await self._read(await super().get(request_id, now=now))


@pytest.mark.concurrency
@pytest.mark.integration
@pytest.mark.parametrize("run", range(3))
@pytest.mark.parametrize(
    ("first", "second"),
    [(S.QUOTED, S.QUOTED), (S.QUOTED, S.LOST), (S.LOST, S.LOST)],
    ids=["quote-vs-quote", "quote-vs-lose", "lose-vs-lose"],
)
async def test_two_admins_racing_on_one_lead_leave_a_true_audit_chain(
    db_engine: AsyncEngine, run: int, first: CustomRequestStatus, second: CustomRequestStatus
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as db, db.begin():
        row = CustomRequestModel(
            name="Race",
            email=f"race-{uuid.uuid4().hex}@example.com",
            phone="+961 1 234 567",
            project_title="Racing lead",
            description="race",
            status=S.CONTACTED,
            contacted_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    lead_id = row.id
    before_read, after_read = asyncio.Barrier(2), asyncio.Barrier(2)

    async def move(target: CustomRequestStatus, amount: int) -> str:
        async with factory() as db, db.begin():
            command = TransitionCustomRequest(
                _SyncedRepository(db, before_read, after_read), SqlAuditWriter(db)
            )
            try:
                await command.execute(
                    custom_request_id=lead_id,
                    target=target,
                    quoted_amount_cents=amount if target is S.QUOTED else None,
                    now=datetime.now(UTC),
                    context=AdminContext(actor_user_id=None, request_id=None, ip_hash=None),  # type: ignore[arg-type]
                )
            except InvalidCustomRequestTransitionError:
                return "refused"
            return "moved"

    outcomes = await asyncio.gather(move(first, 1_000), move(second, 2_000))

    async with factory() as db:
        audits = (
            await db.scalars(
                select(AuditLogModel)
                .where(
                    AuditLogModel.entity_id == lead_id,
                    AuditLogModel.action == "custom_request.transitioned",
                )
                .order_by(AuditLogModel.created_at)
            )
        ).all()
        final = await db.get(CustomRequestModel, lead_id)
    assert final is not None
    assert len(audits) == outcomes.count("moved")
    moves = [((a.before_data or {})["status"], (a.after_data or {})["status"]) for a in audits]
    starts = [before for before, _ in moves]
    assert starts.count("contacted") == 1, f"two writers both started from contacted: {starts}"
    if first is second:
        assert sorted(outcomes) == ["moved", "refused"]
    chain = dict(moves)
    state = "contacted"
    while state in chain:
        state = chain.pop(state)
    assert not chain and state == final.status
    assert final.outcome == ("lost" if final.status == "lost" else None)
    if final.status == "quoted":
        assert (audits[0].after_data or {})["quoted_amount_cents"] == final.quoted_amount_cents
