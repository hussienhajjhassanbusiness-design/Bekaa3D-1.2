from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.core.config import get_settings
from app.engagement.public import referenced_attachment_keys
from app.integrations.storage.factory import private_upload_storage, public_media_storage
from app.integrations.storage.ports import StoragePort

logger = structlog.get_logger()

# Longer than any upload can take, so a file whose row is still being committed is safe.
GRACE_PERIOD = timedelta(hours=24)
PREFIX = "products/"
BATCH = 500


@dataclass(frozen=True)
class ReapTarget:
    """One key prefix and the table whose rows reference files under it."""

    prefix: str
    referenced: Callable[[AsyncSession, list[str]], Awaitable[set[str]]]


async def _product_images(session: AsyncSession, keys: list[str]) -> set[str]:
    return await ProductImageRepository(session).referenced_keys(keys)


PRODUCT_IMAGES = ReapTarget(PREFIX, _product_images)
CUSTOM_REQUEST_ATTACHMENTS = ReapTarget("custom-requests/", referenced_attachment_keys)


async def reap(
    storage: StoragePort,
    session_factory: Any,
    now: datetime,
    target: ReapTarget = PRODUCT_IMAGES,
) -> list[str]:
    """Delete stored files no row references, once older than the grace period (SRS 23)."""
    listed = await storage.list(target.prefix)
    stale = [o.key for o in listed if now - o.modified_at >= GRACE_PERIOD]
    reaped: list[str] = []
    for start in range(0, len(stale), BATCH):
        batch = stale[start : start + BATCH]
        async with session_factory() as session:
            referenced = await target.referenced(session, batch)
        for key in batch:
            if key not in referenced:
                await storage.delete(key)
                reaped.append(key)
    return reaped


async def reap_orphan_files(ctx: dict[str, Any]) -> int:
    """arq job, daily: public product media and private Bring Your Idea attachments.
    Each target runs even if the other fails; the first failure is re-raised afterwards."""
    settings, now = get_settings(), datetime.now(UTC)
    targets = (
        (public_media_storage(settings), PRODUCT_IMAGES),
        (private_upload_storage(settings), CUSTOM_REQUEST_ATTACHMENTS),
    )
    reaped: list[str] = []
    failures: list[Exception] = []
    for storage, target in targets:
        try:
            reaped += await reap(storage, ctx["session_factory"], now, target)
        except Exception as exc:
            await logger.aexception("orphan_reap_failed", prefix=target.prefix)
            failures.append(exc)
    if reaped:
        await logger.ainfo("orphan_files_reaped", count=len(reaped), keys=reaped[:20])
    if failures:
        raise failures[0]
    return len(reaped)
