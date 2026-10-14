from app.integrations.captcha.ports import CaptchaPort, CaptchaRefusedError, CaptchaUnavailableError

# What Cloudflare's public test site keys issue, so a dev frontend works unchanged.
FAKE_CAPTCHA_PASS = "XXXX.DUMMY.TOKEN.XXXX"


class FakeCaptcha(CaptchaPort):
    """Tests and development only: accepts one token, records calls, can play unavailable."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[str] = []

    async def verify(self, token: str) -> None:
        self.calls.append(token)
        if not self.available:
            raise CaptchaUnavailableError("fake captcha switched off")
        if token != FAKE_CAPTCHA_PASS:
            raise CaptchaRefusedError("fake captcha refused the token")
