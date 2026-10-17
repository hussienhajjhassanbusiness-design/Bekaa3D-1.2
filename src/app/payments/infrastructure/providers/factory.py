"""Which payment providers this process may run (VS-023 plan 3.9). Called at boot by
`main.py` and `worker.py`, so a forbidden configuration never serves a request."""

from collections.abc import Callable, Mapping

from app.core.config import Settings
from app.payments.application.ports import PaymentProviderPort
from app.payments.domain.exceptions import PaymentConfigurationError
from app.payments.infrastructure.providers.mock import MockPaymentProvider

DEFAULT_MOCK_SECRET = "mock-webhook-dev-secret"
NONE = "none"
# An allowlist, as the captcha's: "Production" or "prod" is not a mock environment.
_MOCK_DEFAULT_SECRET_OK = frozenset({"development", "test"})
_MOCK_OWN_SECRET_OK = frozenset({"staging"})


def _mock(settings: Settings) -> PaymentProviderPort:
    return MockPaymentProvider(
        redis_url=settings.redis_url,
        webhook_secret=settings.mock_webhook_secret,
        frontend_base_url=settings.frontend_base_url,
    )


ADAPTERS: dict[str, Callable[[Settings], PaymentProviderPort]] = {"mock": _mock}


def configured_payment_providers(settings: Settings) -> Mapping[str, PaymentProviderPort]:
    """Raise PaymentConfigurationError for an unknown name, 'cash', mock in production,
    or mock with the default secret outside development/test. 'none' gives {}."""
    name = settings.payment_provider.strip().lower()
    if name == NONE:
        return {}
    if name not in ADAPTERS:
        raise PaymentConfigurationError(f"PAYMENT_PROVIDER {name!r} has no online adapter.")
    if name == "mock" and settings.environment not in _MOCK_DEFAULT_SECRET_OK:
        if settings.environment not in _MOCK_OWN_SECRET_OK:
            raise PaymentConfigurationError(
                f"The mock payment provider never runs in {settings.environment!r}."
            )
        if settings.mock_webhook_secret == DEFAULT_MOCK_SECRET:
            raise PaymentConfigurationError(
                f"MOCK_WEBHOOK_SECRET must be set in {settings.environment!r}."
            )
    return {name: ADAPTERS[name](settings)}
