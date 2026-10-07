from app.core.config import Settings
from app.integrations.email.console import ConsoleEmailProvider
from app.integrations.email.ports import EmailProviderPort


def get_email_provider(settings: Settings) -> EmailProviderPort:
    if settings.email_provider == "console":
        return ConsoleEmailProvider()
    raise NotImplementedError(
        f"Email provider {settings.email_provider!r} is not implemented yet - "
        "only 'console' exists until a real provider is selected (SRS §30.2)."
    )
