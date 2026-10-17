"""Daily purge of expired idempotency claims (VS-023 plan 2.4; SRS 7.5). Each batch is
its own short transaction with SKIP LOCKED; a capped run resumes the next day."""

from datetime import UTC, datetime
from typing import Any

import structlog

from app.platform.public import idempotency_store

logger = structlog.get_logger()

BATCH_SIZE = 1000
MAX_BATCHES_PER_RUN = 50


async def purge_expired_idempotency_records(
    ctx: dict[str, Any],
    *,
    now: datetime | None = None,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> dict[str, int]:
    """arq job. Returns rows deleted and `truncated` (0 or 1)."""
    moment = now or datetime.now(UTC)
    deleted, truncated = 0, 1
    for _ in range(max_batches):
        async with ctx["session_factory"]() as session, session.begin():
            batch = await idempotency_store(session).purge_expired(now=moment, limit=batch_size)
        deleted += batch
        if batch < batch_size:
            truncated = 0
            break
    if truncated:
        await logger.awarning("idempotency_purge_truncated", deleted=deleted)
    return {"deleted": deleted, "truncated": truncated}
