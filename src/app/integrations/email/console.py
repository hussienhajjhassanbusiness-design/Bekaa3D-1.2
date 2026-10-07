from typing import Any

import structlog

from app.integrations.email.ports import EmailProviderPort

logger = structlog.get_logger()


class ConsoleEmailProvider(EmailProviderPort):
    """Local-dev adapter: logs the email instead of sending it. Selected via
    EMAIL_PROVIDER=console (the .env.example default) until a real provider is
    chosen - see SRS §30.2 (Awaiting Client)."""

    async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
        # Deliberately logs the payload's *keys* and never its values: the
        # payload carries the raw verification token and a token-bearing URL, and
        # a structured log is copied, shipped and retained far more widely than
        # the database is (SEC-26). Recipient and template are safe metadata and
        # are what makes the line useful.
        await logger.ainfo(
            "console_email_send",
            to=to,
            template=template,
            payload_keys=sorted(payload),
        )
