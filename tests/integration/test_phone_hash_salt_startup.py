"""Boot refuses a short or placeholder PHONE_HASH_SALT outside development and test, in the
API and the worker alike (VS-028 plan Q5). Every row runs through `app.main.lifespan` and
`app.worker.on_startup`, like `tests/integration/payments/test_payment_startup.py`."""

from collections.abc import Callable, Iterator

import pytest

from app.core.config import get_settings
from app.core.security import ConfigurationError
from tests.integration.payments.test_payment_startup import BOOTS, Boot

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

PLACEHOLDER = "generate_with__openssl_rand_hex_32"
GENERATED = "0123456789abcdef" * 4


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str, str], None]]:
    def _set(environment: str, salt: str) -> None:
        # The captcha check runs first and refuses the fake outside development/test.
        monkeypatch.setenv("CAPTCHA_PROVIDER", "turnstile")
        monkeypatch.setenv("TURNSTILE_SECRET", "test-only")
        monkeypatch.setenv("ENVIRONMENT", environment)
        # `none` is allowed everywhere, so only the salt can refuse the boot.
        monkeypatch.setenv("PAYMENT_PROVIDER", "none")
        monkeypatch.setenv("PHONE_HASH_SALT", salt)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@BOOTS
@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize("salt", ["a" * 31, PLACEHOLDER], ids=["short", "placeholder"])
async def test_a_weak_salt_refuses_to_start(
    env: Callable[[str, str], None], boot: Boot, environment: str, salt: str
) -> None:
    env(environment, salt)
    with pytest.raises(ConfigurationError) as raised:
        await boot()
    assert salt not in str(raised.value)


@BOOTS
@pytest.mark.parametrize(
    ("environment", "salt"),
    [
        ("production", GENERATED),
        ("staging", "a" * 32),
        ("development", PLACEHOLDER),
        ("test", "a" * 31),
    ],
    ids=["production-generated", "staging-32", "development-placeholder", "test-short"],
)
async def test_an_allowed_salt_starts(
    env: Callable[[str, str], None], boot: Boot, environment: str, salt: str
) -> None:
    env(environment, salt)
    assert await boot() == {}
