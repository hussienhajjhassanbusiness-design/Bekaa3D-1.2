import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.integrations.storage.ports import (
    InvalidStorageKeyError,
    ObjectNotFoundError,
    ObjectStream,
    StoragePort,
    StoredObject,
)

TEMP_PREFIX = ".tmp-"
CHUNK_BYTES = 64 * 1024


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

    def _size(self, path: Path, key: str) -> int:
        if not path.is_file():
            raise ObjectNotFoundError(key)
        return path.stat().st_size

    async def open(self, key: str) -> ObjectStream:
        """Checks now, opens on the first chunk: a response that never streams holds no file."""
        path = self._path(key)
        size = await asyncio.to_thread(self._size, path, key)
        return ObjectStream(size=size, chunks=_chunks(path, key))

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


async def _chunks(path: Path, key: str) -> AsyncIterator[bytes]:
    """Once open, the handle pins the file, so a later purge or replace cannot tear the read."""
    try:
        handle: BinaryIO = await asyncio.to_thread(path.open, "rb")
    except FileNotFoundError as exc:
        raise ObjectNotFoundError(key) from exc
    try:
        while chunk := await asyncio.to_thread(handle.read, CHUNK_BYTES):
            yield chunk
    finally:
        handle.close()
