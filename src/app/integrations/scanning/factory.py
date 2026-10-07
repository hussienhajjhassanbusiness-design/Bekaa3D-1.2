from app.core.config import Settings, get_settings
from app.integrations.scanning.clamav import ClamAvScanner
from app.integrations.scanning.fake import FakeScanner
from app.integrations.scanning.ports import MalwareScannerPort


def malware_scanner(settings: Settings) -> MalwareScannerPort:
    if settings.scanner == "clamav":
        return ClamAvScanner(
            settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds
        )
    if settings.scanner == "fake" and settings.environment in {"test", "development"}:
        return FakeScanner()
    raise ValueError(f"Scanner {settings.scanner!r} is not allowed in {settings.environment!r}.")


def get_malware_scanner() -> MalwareScannerPort:
    """FastAPI dependency; tests override it with a FakeScanner."""
    return malware_scanner(get_settings())
