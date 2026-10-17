"""Daily purge of expired Bring Your Idea reference images (VS-034, SRS 13.4, BR-115).
Each batch is its own short transaction using SKIP LOCKED; a capped run resumes next day."""

from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.config import get_settings
from app.engagement.application.commands.purge_expired_attachments import (
    PurgeExpiredAttachments,
)
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.integrations.storage.factory import private_upload_storage
from app.integrations.storage.ports import StoragePort

logger = structlog.get_logger()

BATCH_SIZE = 500
MAX_BATCHES_PER_RUN = 50


async def purge_expired_attachments(
    ctx: dict[str, Any],
    *,
    now: datetime | None = None,
    storage: StoragePort | None = None,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> dict[str, int]:
    """arq job. Returns attachments purged, and `truncated` (0 or 1)."""
    moment = now or datetime.now(UTC)
    files = storage or private_upload_storage(get_settings())
    purged, truncated = 0, True
    for _ in range(max_batches):
        async with ctx["session_factory"]() as session, session.begin():
            count = await PurgeExpiredAttachments(
                SqlCustomRequestRepository(session), files
            ).execute_batch(now=moment, limit=batch_size)
        purged += count
        if count < batch_size:
            truncated = False
            break
    if purged:
        await logger.ainfo("expired_attachments_purged", count=purged, truncated=truncated)
    return {"attachments": purged, "truncated": int(truncated)}
