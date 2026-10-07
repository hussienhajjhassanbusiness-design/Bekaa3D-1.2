"""The clamd INSTREAM client, against an in-process server speaking the same protocol.
The last test runs against a real clamd when docker compose has one up."""

import asyncio
import socket
import struct
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest

from app.integrations.scanning.clamav import CHUNK_BYTES, ClamAvScanner
from app.integrations.scanning.fake import EICAR
from app.integrations.scanning.ports import ScannerUnavailableError, ScanResult

Responder = Callable[[bytes], bytes | None]


@asynccontextmanager
async def _serve(respond: Responder, received: list[bytes]) -> AsyncIterator[int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readuntil(b"\0") == b"zINSTREAM\0"
        body = b""
        while size := struct.unpack("!I", await reader.readexactly(4))[0]:
            body += await reader.readexactly(size)
        received.append(body)
        reply = respond(body)
        if reply is not None:
            writer.write(reply)
            await writer.drain()
            writer.close()
        else:
            await asyncio.sleep(1)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    async with server:
        yield server.sockets[0].getsockname()[1]


@pytest.fixture
def received() -> list[bytes]:
    return []


async def _scan(
    respond: Responder, received: list[bytes], data: bytes, wait_seconds: float = 5.0
) -> ScanResult:
    async with _serve(respond, received) as port:
        return await ClamAvScanner("127.0.0.1", port, wait_seconds).scan(data)


async def test_ok_is_clean_and_every_chunk_arrives(received: list[bytes]) -> None:
    data = bytes(range(256)) * (CHUNK_BYTES // 256 * 2 + 3)
    result = await _scan(lambda _: b"stream: OK\0", received, data)
    assert result.clean and result.signature is None
    assert received == [data]


async def test_found_is_infected_with_the_signature(received: list[bytes]) -> None:
    result = await _scan(lambda _: b"stream: Eicar-Test-Signature FOUND\0", received, EICAR)
    assert not result.clean and result.signature == "Eicar-Test-Signature"


@pytest.mark.parametrize(
    "reply", [b"INSTREAM size limit exceeded. ERROR\0", b"stream: \0", b"garbage\0"]
)
async def test_anything_but_a_verdict_fails_closed(received: list[bytes], reply: bytes) -> None:
    with pytest.raises(ScannerUnavailableError):
        await _scan(lambda _: reply, received, b"x")


async def test_a_silent_scanner_times_out_and_fails_closed(received: list[bytes]) -> None:
    with pytest.raises(ScannerUnavailableError):
        await _scan(lambda _: None, received, b"x", wait_seconds=0.2)


async def test_an_unreachable_scanner_fails_closed() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(ScannerUnavailableError):
        await ClamAvScanner("127.0.0.1", port, 2.0).scan(b"x")


@pytest.mark.clamav
async def test_a_real_clamd_flags_eicar_and_passes_clean_bytes() -> None:
    try:
        with socket.create_connection(("127.0.0.1", 3310), timeout=1):
            pass
    except OSError:
        pytest.skip("no clamd on 127.0.0.1:3310 (docker compose up clamav)")
    scanner = ClamAvScanner("127.0.0.1", 3310, 30.0)
    assert not (await scanner.scan(EICAR)).clean
    assert (await scanner.scan(b"an ordinary harmless payload")).clean
