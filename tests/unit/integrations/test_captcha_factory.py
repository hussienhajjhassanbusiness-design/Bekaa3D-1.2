"""ADR-026: the fake captcha can never stand in for Turnstile outside test and development."""

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.integrations.captcha.factory import captcha_verifier
from app.integrations.captcha.fake import FakeCaptcha
from app.integrations.captcha.turnstile import TurnstileCaptcha


def _settings(provider: str, environment: str, secret: str = "s3cret") -> Settings:
    return Settings.model_construct(
        captcha_provider=provider,
        environment=environment,
        turnstile_secret=secret,
        turnstile_timeout_seconds=5.0,
    )


@pytest.mark.parametrize("environment", ["production", "staging", "development", "test"])
def test_turnstile_is_built_in_every_environment(environment: str) -> None:
    assert isinstance(captcha_verifier(_settings("turnstile", environment)), TurnstileCaptcha)


@pytest.mark.parametrize("environment", ["test", "development"])
def test_the_fake_is_allowed_only_for_tests_and_development(environment: str) -> None:
    assert isinstance(captcha_verifier(_settings("fake", environment)), FakeCaptcha)


@pytest.mark.parametrize(
    ("provider", "environment"),
    [
        ("fake", "production"),
        ("fake", "staging"),
        ("fake", "prod"),
        ("fake", "Production"),
        ("fake", "Development"),
        ("fake", ""),
        ("none", "development"),
        ("", "test"),
    ],
)
def test_anything_else_refuses_to_start(provider: str, environment: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        captcha_verifier(_settings(provider, environment))


def test_turnstile_without_a_secret_refuses_to_start() -> None:
    with pytest.raises(ValueError, match="TURNSTILE_SECRET"):
        captcha_verifier(_settings("turnstile", "production", secret=""))


@pytest.mark.parametrize(
    ("provider", "environment", "secret"),
    [("fake", "production", "s3cret"), ("turnstile", "production", "")],
)
async def test_the_api_refuses_to_start_with_a_bad_captcha_config(
    monkeypatch: pytest.MonkeyPatch, provider: str, environment: str, secret: str
) -> None:
    import app.main as main_module

    bad = _settings(provider, environment, secret=secret)
    monkeypatch.setattr(main_module, "get_settings", lambda: bad)
    monkeypatch.setattr(main_module, "make_engine", _must_not_run)
    with pytest.raises(ValueError, match=r"not allowed|TURNSTILE_SECRET"):
        async with main_module.lifespan(FastAPI()):
            pass


def _must_not_run(*_args: object) -> None:
    raise AssertionError("the database was touched before the captcha config was checked")
