import httpx
import structlog

from app.integrations.captcha.ports import CaptchaPort, CaptchaRefusedError, CaptchaUnavailableError

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# The visitor's fault: answered as CAPTCHA_INVALID. Anything else is ours or Cloudflare's.
_REFUSAL_CODES = frozenset(
    {"missing-input-response", "invalid-input-response", "timeout-or-duplicate"}
)

logger = structlog.get_logger()


class TurnstileCaptcha(CaptchaPort):
    """Cloudflare Turnstile `siteverify`. The token is never logged."""

    def __init__(
        self,
        secret: str,
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._secret = secret
        self._timeout = timeout_seconds
        self._transport = transport

    async def verify(self, token: str) -> None:
        if not token:
            raise CaptchaRefusedError("empty captcha token")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    SITEVERIFY_URL, data={"secret": self._secret, "response": token}
                )
            response.raise_for_status()
            outcome = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("captcha_unavailable", reason=type(exc).__name__)
            raise CaptchaUnavailableError(f"siteverify failed: {type(exc).__name__}") from exc
        _judge(outcome)


def _judge(outcome: object) -> None:
    if not isinstance(outcome, dict):
        raise CaptchaUnavailableError("siteverify answered a non-object")
    if outcome.get("success") is True:
        return
    codes = outcome.get("error-codes")
    codes = {str(code) for code in codes} if isinstance(codes, list) else set()
    if codes and codes <= _REFUSAL_CODES:
        raise CaptchaRefusedError(f"turnstile refused: {sorted(codes)}")
    logger.error("captcha_unavailable", error_codes=sorted(codes))
    raise CaptchaUnavailableError(f"turnstile gave no verdict: {sorted(codes)}")
