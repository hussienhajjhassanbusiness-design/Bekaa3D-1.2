from app.core.config import Settings, get_settings
from app.integrations.captcha.fake import FakeCaptcha
from app.integrations.captcha.ports import CaptchaPort
from app.integrations.captcha.turnstile import TurnstileCaptcha


def captcha_verifier(settings: Settings) -> CaptchaPort:
    """Allowlist, as the scanner's: the fake never runs outside test and development."""
    if settings.captcha_provider == "turnstile":
        if not settings.turnstile_secret:
            raise ValueError("Captcha provider 'turnstile' needs TURNSTILE_SECRET.")
        return TurnstileCaptcha(
            settings.turnstile_secret, timeout_seconds=settings.turnstile_timeout_seconds
        )
    if settings.captcha_provider == "fake" and settings.environment in {"test", "development"}:
        return FakeCaptcha()
    raise ValueError(
        f"Captcha provider {settings.captcha_provider!r} is not allowed in "
        f"{settings.environment!r}."
    )


def get_captcha_verifier() -> CaptchaPort:
    """FastAPI dependency; tests override it with a FakeCaptcha."""
    return captcha_verifier(get_settings())
