from app.integrations.scanning.ports import MalwareScannerPort, ScannerUnavailableError, ScanResult

# The industry-standard harmless test signature every scanner reports as infected.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeScanner(MalwareScannerPort):
    """Tests only: flags EICAR, records what it saw, and can play unavailable."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.scanned: list[bytes] = []

    async def scan(self, data: bytes) -> ScanResult:
        if not self.available:
            raise ScannerUnavailableError("fake scanner switched off")
        self.scanned.append(data)
        if EICAR in data:
            return ScanResult(clean=False, signature="Eicar-Test-Signature")
        return ScanResult(clean=True)
