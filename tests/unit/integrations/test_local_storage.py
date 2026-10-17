from pathlib import Path

import pytest

from app.integrations.storage.local import CHUNK_BYTES, LocalStorage
from app.integrations.storage.ports import InvalidStorageKeyError, ObjectNotFoundError


async def test_put_exists_list_delete_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("products/a.jpg", b"one")
    await storage.put("products/a.jpg", b"two")
    assert await storage.exists("products/a.jpg")
    assert (tmp_path / "products" / "a.jpg").read_bytes() == b"two"
    assert [o.key for o in await storage.list("products/")] == ["products/a.jpg"]
    await storage.delete("products/a.jpg")
    await storage.delete("products/a.jpg")
    assert not await storage.exists("products/a.jpg")
    assert await storage.list("products/") == []


async def test_a_write_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    await LocalStorage(tmp_path).put("products/b.png", b"data")
    assert [p.name for p in (tmp_path / "products").iterdir()] == ["b.png"]


@pytest.mark.parametrize(
    "key", ["", "/etc/passwd", "../outside", "products/../../x", "products\\..\\x", "a/../../b"]
)
async def test_keys_cannot_escape_the_root(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path / "root")
    with pytest.raises(InvalidStorageKeyError):
        await storage.put(key, b"x")
    assert not (tmp_path / "outside").exists() and not (tmp_path / "x").exists()


async def test_listing_a_missing_prefix_is_empty(tmp_path: Path) -> None:
    assert await LocalStorage(tmp_path).list("products/") == []


async def test_open_streams_the_whole_object_in_chunks(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    data = bytes(range(256)) * (CHUNK_BYTES // 128 + 3)
    await storage.put("custom-requests/a.png", data)
    stream = await storage.open("custom-requests/a.png")
    chunks = [chunk async for chunk in stream.chunks]
    assert stream.size == len(data) and b"".join(chunks) == data
    assert len(chunks) > 1 and max(map(len, chunks)) <= CHUNK_BYTES


@pytest.mark.parametrize("key", ["custom-requests/missing.png", "custom-requests"])
async def test_open_refuses_a_missing_object_before_streaming(tmp_path: Path, key: str) -> None:
    (tmp_path / "custom-requests").mkdir()
    with pytest.raises(ObjectNotFoundError):
        await LocalStorage(tmp_path).open(key)


@pytest.mark.parametrize("key", ["../outside.png", "/etc/passwd", "a\..\b"])
async def test_open_cannot_escape_the_root(tmp_path: Path, key: str) -> None:
    with pytest.raises(InvalidStorageKeyError):
        await LocalStorage(tmp_path / "root").open(key)
