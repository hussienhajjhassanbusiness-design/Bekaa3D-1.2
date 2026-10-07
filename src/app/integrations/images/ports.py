from abc import ABC, abstractmethod
from dataclasses import dataclass


class ImageRejectedError(ValueError):
    """Not an accepted image, by content - never by filename or Content-Type (SEC-13)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SanitizedImage:
    """Freshly encoded pixels only: no EXIF, ICC, XMP or trailing bytes (SEC-14)."""

    data: bytes
    extension: str
    content_type: str
    width: int
    height: int


class ImageSanitizerPort(ABC):
    @abstractmethod
    async def sanitize(self, data: bytes) -> SanitizedImage:
        """Re-encode an accepted image, or raise ImageRejectedError."""
        raise NotImplementedError
