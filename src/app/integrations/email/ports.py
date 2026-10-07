from abc import ABC, abstractmethod
from typing import Any


class EmailProviderPort(ABC):
    @abstractmethod
    async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
        """Send one email. Must raise on failure so the outbox worker can retry -
        never swallow errors here."""
        raise NotImplementedError
