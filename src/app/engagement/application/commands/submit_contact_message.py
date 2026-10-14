from app.engagement.application.ports import ContactMessageStore
from app.engagement.domain.contact_message import ContactDetails, ContactMessage


class SubmitContactMessage:
    """Stores one message in the admin queue (FR-16). Captcha and limits run before this."""

    def __init__(self, messages: ContactMessageStore) -> None:
        self._messages = messages

    async def execute(self, details: ContactDetails) -> ContactMessage:
        return await self._messages.add(details)
