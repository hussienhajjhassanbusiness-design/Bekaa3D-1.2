"""Which payment providers may boot where (VS-023 plan 3.9, 6.1)."""

from collections.abc import Iterator

import pytest

from app.core.config import Settings
from app.payments.domain.exceptions import PaymentConfigurationError
from app.payments.infrastructure.providers import factory
from app.payments.infrastructure.providers.factory import (
    DEFAULT_MOCK_SECRET,
    configured_payment_providers,
)
from app.payments.infrastructure.providers.manual import ManualPaymentProvider
from app.payments.infrastructure.providers.mock import MockPaymentProvider


def _settings(provider: str, environment: str, secret: str = DEFAULT_MOCK_SECRET) -> Settings:
    return Settings.model_construct(
        payment_provider=provider,
        environment=environment,
        mock_webhook_secret=secret,
        redis_url="redis://localhost:6379/0",
        frontend_base_url="http://localhost:3000",
    )


@pytest.mark.parametrize("environment", ["development", "test"])
def test_mock_boots_in_development_and_test_with_the_default_secret(environment: str) -> None:
    providers = configured_payment_providers(_settings("mock", environment))
    assert list(providers) == ["mock"]
    assert isinstance(providers["mock"], MockPaymentProvider)


def test_mock_boots_in_staging_only_with_its_own_secret() -> None:
    assert list(configured_payment_providers(_settings("mock", "staging", "s3cret"))) == ["mock"]
    with pytest.raises(PaymentConfigurationError, match="MOCK_WEBHOOK_SECRET"):
        configured_payment_providers(_settings("mock", "staging"))


@pytest.mark.parametrize("environment", ["production", "Production", "prod", ""])
def test_mock_never_boots_outside_its_allowlist(environment: str) -> None:
    with pytest.raises(PaymentConfigurationError, match="never runs"):
        configured_payment_providers(_settings("mock", environment, "s3cret"))


@pytest.mark.parametrize("name", ["cash", "whish", "", "stripe"])
def test_cash_and_unknown_names_refuse(name: str) -> None:
    with pytest.raises(PaymentConfigurationError, match="no online adapter"):
        configured_payment_providers(_settings(name, "development"))


@pytest.mark.parametrize("environment", ["production", "staging", "development", "test"])
def test_manual_boots_in_every_environment(environment: str) -> None:
    """ADR-049 d4: V1's online provider; it holds no secret and calls nothing."""
    providers = configured_payment_providers(_settings(" Manual ", environment))
    assert list(providers) == ["manual"]
    adapter = providers["manual"]
    assert isinstance(adapter, ManualPaymentProvider)
    assert (adapter.supports_status_query, adapter.accepts_webhooks) == (False, False)


@pytest.mark.parametrize("environment", ["production", "staging", "development"])
def test_none_configures_no_online_provider(environment: str) -> None:
    assert configured_payment_providers(_settings("none", environment)) == {}
    assert configured_payment_providers(_settings(" None ", environment)) == {}


@pytest.fixture
def stub_adapter() -> Iterator[object]:
    stub = object()
    factory.ADAPTERS["stub"] = lambda settings: stub  # type: ignore[assignment,return-value]
    yield stub
    del factory.ADAPTERS["stub"]


def test_a_registered_real_adapter_boots_in_production(stub_adapter: object) -> None:
    assert configured_payment_providers(_settings("stub", "production")) == {"stub": stub_adapter}
