from datetime import datetime

from app.engagement.application.ports import CustomRequestStore
from app.integrations.storage.ports import StoragePort


class PurgeExpiredAttachments:
    """Deletes expired reference images from disk, then their rows (SRS 13.4, BR-115).
    Files first: a crash leaves rows the next run finishes, as a missing file is no error."""

    def __init__(self, requests: CustomRequestStore, storage: StoragePort) -> None:
        self._requests = requests
        self._storage = storage

    async def execute_batch(self, *, now: datetime, limit: int) -> int:
        batch = await self._requests.lock_expired_attachments(now=now, limit=limit)
        for attachment in batch:
            await self._storage.delete(attachment.storage_key)
        return await self._requests.delete_attachments([a.id for a in batch])
