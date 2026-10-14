"""Captcha on the five public forms (SEC-12, ADR-025); refusal and outage answers per ADR-026."""

from typing import Annotated, Any

from pydantic import Field

from app.api.text import PlainStr
from app.core.exceptions import ApiError
from app.integrations.captcha.ports import CaptchaPort, CaptchaRefusedError, CaptchaUnavailableError

# Turnstile tokens are at most 2048 characters.
CaptchaToken = Annotated[
    PlainStr, Field(max_length=2048, description="Cloudflare Turnstile token.")
]

OUTAGE_RETRY_AFTER_SECONDS = 30

CAPTCHA_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "`CAPTCHA_INVALID` - the captcha token was empty or refused."},
    503: {"description": "`SERVICE_UNAVAILABLE` - captcha could not be verified; nothing done."},
}


async def require_captcha(token: str, verifier: CaptchaPort) -> None:
    """Fails closed: no verdict is never treated as a pass."""
    try:
        await verifier.verify(token)
    except CaptchaRefusedError as exc:
        raise ApiError(
            status_code=400,
            code="CAPTCHA_INVALID",
            title="Captcha refused",
            detail="The captcha token is empty, invalid, expired or already used.",
        ) from exc
    except CaptchaUnavailableError as exc:
        raise ApiError(
            status_code=503,
            code="SERVICE_UNAVAILABLE",
            title="Service temporarily unavailable",
            detail="Captcha verification is temporarily unavailable. Retry later.",
            headers={"Retry-After": str(OUTAGE_RETRY_AFTER_SECONDS)},
        ) from exc
