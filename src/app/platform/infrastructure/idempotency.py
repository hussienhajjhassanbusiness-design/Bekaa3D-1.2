"""`SqlIdempotencyStore` (VS-023 plan 3.7). Single statements in the caller's session;
it never commits. Requires READ COMMITTED, so the read after a conflict sees the winner."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.idempotency import (
    DONE,
    IN_PROGRESS,
    Claim,
    Conflict,
    InProgress,
    NewClaim,
    Replay,
)
from app.platform.infrastructure.models import IdempotencyRecordModel

_R = IdempotencyRecordModel


class SqlIdempotencyStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        scope: str,
        user_id: UUID | None,
        key: str,
        request_hash: str,
        expires_at: datetime,
    ) -> Claim:
        # Twice at most: an expired rival may be purged between the insert and the read.
        for _ in range(2):
            inserted = await self._session.scalar(
                postgresql.insert(_R)
                .values(
                    scope=scope,
                    user_id=user_id,
                    key=key,
                    request_hash=request_hash,
                    state=IN_PROGRESS,
                    expires_at=expires_at,
                )
                .on_conflict_do_nothing(constraint="uq_idempotency_records_scope_user_key")
                .returning(_R.id)
            )
            if inserted is not None:
                return NewClaim(inserted)
            row = (
                await self._session.execute(
                    select(
                        _R.request_hash, _R.state, _R.resource_id, _R.status_code, _R.response_body
                    ).where(
                        _R.scope == scope, _R.user_id.is_not_distinct_from(user_id), _R.key == key
                    )
                )
            ).first()
            if row is None:
                continue
            if row.request_hash != request_hash:
                return Conflict()
            if row.state == DONE:
                return Replay(row.status_code, row.response_body)
            return InProgress(row.resource_id)
        raise RuntimeError("idempotency claim neither inserted nor found")

    async def attach(self, record_id: UUID, *, resource_id: UUID) -> None:
        await self._session.execute(
            update(_R).where(_R.id == record_id).values(resource_id=resource_id)
        )

    async def complete(self, record_id: UUID, *, status_code: int, body: dict[str, Any]) -> None:
        await self._session.execute(
            update(_R)
            .where(_R.id == record_id)
            .values(state=DONE, status_code=status_code, response_body=body)
        )

    async def purge_expired(self, *, now: datetime, limit: int) -> int:
        batch = (
            select(_R.id)
            .where(_R.expires_at < now)
            .order_by(_R.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(delete(_R).where(_R.id.in_(batch)).returning(_R.id))
        return len(result.all())
