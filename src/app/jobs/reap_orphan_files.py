from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.core.config import get_settings
from app.integrations.storage.factory import public_media_storage
from app.integrations.storage.ports import StoragePort

logger = structlog.get_logger()

# Longer than any upload can take, so a file whose row is still being committed is safe.
GRACE_PERIOD = timedelta(hours=24)
PREFIX = "products/"
BATCH = 500


async def reap(storage: StoragePort, session_factory: Any, now: datetime) -> list[str]:
    """Delete stored files no row references, once older than the grace period (SRS 23)."""
    stale = [o.key for o in await storage.list(PREFIX) if now - o.modified_at >= GRACE_PERIOD]
    reaped: list[str] = []
    for start in range(0, len(stale), BATCH):
        batch = stale[start : start + BATCH]
        async with session_factory() as session:
            referenced = await ProductImageRepository(session).referenced_keys(batch)
        for key in batch:
            if key not in referenced:
                await storage.delete(key)
                reaped.append(key)
    return reaped


async def reap_orphan_files(ctx: dict[str, Any]) -> int:
    """arq job, daily: storage writes are not transactional with Postgres."""
    reaped = await reap(
        public_media_storage(get_settings()), ctx["session_factory"], datetime.now(UTC)
    )
    if reaped:
        await logger.ainfo("orphan_files_reaped", count=len(reaped), keys=reaped[:20])
    return len(reaped)
