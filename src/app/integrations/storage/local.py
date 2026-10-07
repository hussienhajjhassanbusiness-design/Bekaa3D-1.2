import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.integrations.storage.ports import InvalidStorageKeyError, StoragePort, StoredObject

TEMP_PREFIX = ".tmp-"


class LocalStorage(StoragePort):
    """A directory on the server's volume; keys are POSIX-style relative paths."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        posix = PurePosixPath(key)
        if not key or posix.is_absolute() or ".." in posix.parts or "\\" in key:
            raise InvalidStorageKeyError(key)
        path = (self._root / posix).resolve()
        if not path.is_relative_to(self._root):
            raise InvalidStorageKeyError(key)
        return path

    def _put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{TEMP_PREFIX}{uuid.uuid4().hex}")
        try:
            temp.write_bytes(data)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._put, key, data)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)

    def _list(self, prefix: str) -> list[StoredObject]:
        base = self._path(prefix.rstrip("/")) if prefix.strip("/") else self._root
        if not base.is_dir():
            return []
        return [
            StoredObject(
                key=path.relative_to(self._root).as_posix(),
                modified_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
            )
            for path in base.rglob("*")
            if path.is_file()
        ]

    async def list(self, prefix: str) -> list[StoredObject]:
        return await asyncio.to_thread(self._list, prefix)
