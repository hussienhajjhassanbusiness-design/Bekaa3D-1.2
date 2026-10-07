"""SEC-15: the EICAR-only fake can never stand in for ClamAV outside test and development."""

import pytest

from app.core.config import Settings
from app.integrations.scanning.clamav import ClamAvScanner
from app.integrations.scanning.factory import malware_scanner
from app.integrations.scanning.fake import FakeScanner


def _settings(scanner: str, environment: str) -> Settings:
    return Settings.model_construct(
        scanner=scanner,
        environment=environment,
        clamav_host="clamav",
        clamav_port=3310,
        clamav_timeout_seconds=30.0,
    )


@pytest.mark.parametrize("environment", ["production", "staging", "development", "test"])
def test_clamav_is_built_in_every_environment(environment: str) -> None:
    assert isinstance(malware_scanner(_settings("clamav", environment)), ClamAvScanner)


@pytest.mark.parametrize("environment", ["test", "development"])
def test_the_fake_is_allowed_only_for_tests_and_development(environment: str) -> None:
    assert isinstance(malware_scanner(_settings("fake", environment)), FakeScanner)


@pytest.mark.parametrize(
    ("scanner", "environment"),
    [("fake", "production"), ("fake", "staging"), ("none", "production"), ("", "test")],
)
def test_anything_else_refuses_to_start(scanner: str, environment: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        malware_scanner(_settings(scanner, environment))
