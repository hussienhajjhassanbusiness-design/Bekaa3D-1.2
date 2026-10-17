"""Seeding Bring Your Idea attachments straight through the repository, for job tests."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.engagement.domain.custom_request import CustomRequestDetails, NewAttachment
from app.engagement.infrastructure.custom_requests import SqlCustomRequestRepository
from app.engagement.infrastructure.models import CustomRequestAttachmentModel, CustomRequestModel
from app.integrations.storage.ports import StoragePort

DETAILS = CustomRequestDetails.of(
    name="Seed",
    email="seed@example.com",
    phone="+961 1 234 567",
    project_title="Seeded lead",
    description="seeded",
)


async def seed_request(
    engine: AsyncEngine,
    storage: StoragePort,
    *,
    expires_at: datetime,
    files: int = 2,
    write_files: bool = True,
) -> tuple[uuid.UUID, list[str]]:
    """A request whose attachments expire at `expires_at`; returns its id and storage keys."""
    keys = [f"custom-requests/{uuid.uuid4()}.png" for _ in range(files)]
    if write_files:
        for key in keys:
            await storage.put(key, b"png-bytes")
    attachments = [NewAttachment(key, "photo.png", "image/png", 9, "0" * 64) for key in keys]
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        request = await SqlCustomRequestRepository(session).add(
            DETAILS,
            attachments,
            submitted_at=expires_at - timedelta(days=90),
            expires_at=expires_at,
        )
    return request.id, keys


async def surviving_keys(engine: AsyncEngine, keys: list[str]) -> set[str]:
    async with async_sessionmaker(engine)() as session:
        stmt = select(CustomRequestAttachmentModel.storage_key).where(
            CustomRequestAttachmentModel.storage_key.in_(keys)
        )
        return set((await session.scalars(stmt)).all())


async def request_exists(engine: AsyncEngine, request_id: uuid.UUID) -> bool:
    async with async_sessionmaker(engine)() as session:
        return await session.get(CustomRequestModel, request_id) is not None
