from abc import ABC, abstractmethod


class CaptchaRefusedError(Exception):
    """The provider judged the token bad: missing, invalid, expired or reused."""


class CaptchaUnavailableError(RuntimeError):
    """No verdict (outage or misconfiguration); callers fail closed (ADR-026)."""


class CaptchaPort(ABC):
    @abstractmethod
    async def verify(self, token: str) -> None:
        """Return only for a token the provider accepted; never guess."""
        raise NotImplementedError
