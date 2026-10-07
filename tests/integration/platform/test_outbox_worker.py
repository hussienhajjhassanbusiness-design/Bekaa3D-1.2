import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.email.ports import EmailProviderPort
from app.jobs import outbox as outbox_job
from app.platform.infrastructure.models import EmailOutboxModel
from app.platform.infrastructure.repositories import EmailOutboxRepository


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


async def _empty_the_queue(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Other tests (every registration writes one) leave pending outbox rows
    behind, and dispatch_outbox claims only the BATCH_SIZE oldest. Without this
    the message under test can sit outside the batch and the assertion fails
    for reasons that have nothing to do with the worker."""
    async with session_factory() as session, session.begin():
        await session.execute(
            update(EmailOutboxModel)
            .where(EmailOutboxModel.status == "pending")
            .values(status="sent", sent_at=datetime.now(UTC))
        )


@pytest.mark.integration
async def test_dispatch_outbox_sends_a_pending_message_and_marks_it_sent(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _empty_the_queue(session_factory)

    async with session_factory() as session, session.begin():
        repo = EmailOutboxRepository(session)
        message = await repo.add(
            user_id=None,
            recipient_email=_unique_email(),
            template="verification_email",
            payload={"token": "abc"},
        )

    processed = await outbox_job.dispatch_outbox({"session_factory": session_factory})
    assert processed >= 1

    async with session_factory() as session:
        row = await session.get(EmailOutboxModel, message.id)
        assert row is not None
        assert row.status == "sent"
        assert row.sent_at is not None


@pytest.mark.integration
async def test_dispatch_outbox_retries_on_provider_failure(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    class FailingProvider(EmailProviderPort):
        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(outbox_job, "get_email_provider", lambda settings: FailingProvider())
    await _empty_the_queue(session_factory)

    async with session_factory() as session, session.begin():
        repo = EmailOutboxRepository(session)
        message = await repo.add(
            user_id=None,
            recipient_email=_unique_email(),
            template="verification_email",
            payload={"token": "abc"},
        )

    await outbox_job.dispatch_outbox({"session_factory": session_factory})

    async with session_factory() as session:
        row = await session.get(EmailOutboxModel, message.id)
        assert row is not None
        assert row.status == "pending"
        assert row.attempt_count == 1
        assert row.last_error is not None
        assert row.send_after > datetime.now(UTC)


@pytest.mark.integration
async def test_dispatch_outbox_marks_message_failed_after_max_attempts(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    class FailingProvider(EmailProviderPort):
        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(outbox_job, "get_email_provider", lambda settings: FailingProvider())
    await _empty_the_queue(session_factory)

    async with session_factory() as session, session.begin():
        repo = EmailOutboxRepository(session)
        message = await repo.add(
            user_id=None,
            recipient_email=_unique_email(),
            template="verification_email",
            payload={"token": "abc"},
        )

    for _ in range(5):
        async with session_factory() as session, session.begin():
            row = await session.get(EmailOutboxModel, message.id)
            assert row is not None
            row.send_after = datetime.now(UTC)  # force it due immediately for the next claim
        await outbox_job.dispatch_outbox({"session_factory": session_factory})

    async with session_factory() as session:
        row = await session.get(EmailOutboxModel, message.id)
        assert row is not None
        assert row.status == "failed"
        assert row.attempt_count == 5
