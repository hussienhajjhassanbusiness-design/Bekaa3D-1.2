import asyncio
import struct

from app.integrations.scanning.ports import MalwareScannerPort, ScannerUnavailableError, ScanResult

CHUNK_BYTES = 64 * 1024
MAX_REPLY_BYTES = 4096


class ClamAvScanner(MalwareScannerPort):
    """clamd `INSTREAM` over TCP: length-prefixed chunks, a zero-length end, one reply."""

    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_seconds

    async def scan(self, data: bytes) -> ScanResult:
        try:
            reply = await asyncio.wait_for(self._exchange(data), timeout=self._timeout)
        except (
            OSError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as exc:
            raise ScannerUnavailableError(f"clamd unreachable: {exc!r}") from exc
        return _parse(reply)

    async def _exchange(self, data: bytes) -> bytes:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b"zINSTREAM\0")
            for start in range(0, len(data), CHUNK_BYTES):
                chunk = data[start : start + CHUNK_BYTES]
                writer.write(struct.pack("!I", len(chunk)) + chunk)
                await writer.drain()
            writer.write(struct.pack("!I", 0))
            await writer.drain()
            return await reader.readuntil(b"\0")
        finally:
            writer.close()
            await writer.wait_closed()


def _parse(reply: bytes) -> ScanResult:
    text = reply.rstrip(b"\0").decode("utf-8", "replace").strip()
    verdict = text.split(":", 1)[-1].strip()
    if verdict == "OK":
        return ScanResult(clean=True)
    if verdict.endswith(" FOUND"):
        return ScanResult(clean=False, signature=verdict.removesuffix(" FOUND"))
    raise ScannerUnavailableError(f"clamd gave no verdict: {text[:MAX_REPLY_BYTES]!r}")
