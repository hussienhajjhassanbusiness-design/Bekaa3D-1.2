from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class InvalidStorageKeyError(ValueError):
    """A key that is absolute, empty or climbs out of the storage root."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    modified_at: datetime


class StoragePort(ABC):
    """Keyed blob storage (ADR-013). Writes are not transactional with Postgres,
    which is why `reap_orphan_files` exists (SRS 23)."""

    @abstractmethod
    async def put(self, key: str, data: bytes) -> None:
        """Write atomically: a reader sees the whole object or none of it."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object; a missing one is not an error."""
        raise NotImplementedError

    @abstractmethod
    async def list(self, prefix: str) -> list[StoredObject]: ...
