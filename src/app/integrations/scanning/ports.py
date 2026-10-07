from abc import ABC, abstractmethod
from dataclasses import dataclass


class ScannerUnavailableError(RuntimeError):
    """The scanner could not give a verdict; callers must fail closed (VS-014)."""


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str | None = None


class MalwareScannerPort(ABC):
    @abstractmethod
    async def scan(self, data: bytes) -> ScanResult:
        """A verdict, or ScannerUnavailableError - never a guess."""
        raise NotImplementedError
