from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.public import active_administrator_ids


class IdentityAdministratorDirectory:
    """`AdministratorDirectory` over Identity's public surface, in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_administrator_ids(self) -> list[UUID]:
        return await active_administrator_ids(self._session)
