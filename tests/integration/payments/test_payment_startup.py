"""Boot refuses a forbidden payment configuration, in the API and in the worker alike
(VS-023 plan 3.9). Every row runs through `app.main.lifespan` and `app.worker.on_startup`."""

from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI

from app.core.config import get_settings
from app.main import lifespan
from app.payments.domain.exceptions import PaymentConfigurationError
from app.worker import on_shutdown, on_startup

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

Boot = Callable[[], Awaitable[dict[str, Any]]]


async def _api() -> dict[str, Any]:
    app = FastAPI()
    async with lifespan(app):
        return dict(app.state.payment_providers)


async def _worker() -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    await on_startup(ctx)
    try:
        return dict(ctx["payment_providers"])
    finally:
        await on_shutdown(ctx)


BOOTS = pytest.mark.parametrize("boot", [_api, _worker], ids=["main.py", "worker.py"])


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    def _set(environment: str, provider: str, secret: str | None = None) -> None:
        # The captcha check runs first and refuses the fake outside development/test.
        monkeypatch.setenv("CAPTCHA_PROVIDER", "turnstile")
        monkeypatch.setenv("TURNSTILE_SECRET", "test-only")
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.setenv("PAYMENT_PROVIDER", provider)
        if secret is not None:
            monkeypatch.setenv("MOCK_WEBHOOK_SECRET", secret)
        else:
            monkeypatch.delenv("MOCK_WEBHOOK_SECRET", raising=False)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@BOOTS
@pytest.mark.parametrize(
    ("environment", "provider", "secret"),
    [
        ("production", "mock", None),
        ("production", "mock", "own-secret"),
        ("staging", "mock", None),
        ("development", "cash", None),
        ("development", "nonsense", None),
    ],
)
async def test_a_forbidden_configuration_refuses_to_start(
    env: Callable[..., None], boot: Boot, environment: str, provider: str, secret: str | None
) -> None:
    env(environment, provider, secret)
    with pytest.raises(PaymentConfigurationError):
        await boot()


@BOOTS
@pytest.mark.parametrize(
    ("environment", "provider", "secret", "expected"),
    [
        ("production", "none", None, []),
        ("staging", "mock", "own-secret", ["mock"]),
        ("development", "mock", None, ["mock"]),
        ("test", "mock", None, ["mock"]),
    ],
)
async def test_an_allowed_configuration_starts(
    env: Callable[..., None],
    boot: Boot,
    environment: str,
    provider: str,
    secret: str | None,
    expected: list[str],
) -> None:
    env(environment, provider, secret)
    assert list(await boot()) == expected
