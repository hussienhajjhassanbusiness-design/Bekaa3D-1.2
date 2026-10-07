"""Outbox secret-lifecycle and failure-isolation regressions (F02, F05, F12, F13).

No test in this module prints or asserts on a raw token value; the checks are
written as "the stored/logged value is not the secret" rather than by echoing
the secret around.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.integrations.email import console as console_module
from app.integrations.email.console import ConsoleEmailProvider
from app.integrations.email.factory import get_email_provider
from app.jobs import outbox as outbox_job
from app.platform.domain.entities import REDACTED
from app.platform.infrastructure.models import EmailOutboxModel
from app.platform.infrastructure.repositories import EmailOutboxRepository

SECRET = "a-secret-token-value-that-must-not-persist"


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


async def _empty_the_queue(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            update(EmailOutboxModel)
            .where(EmailOutboxModel.status == "pending")
            .values(status="sent", sent_at=datetime.now(UTC))
        )


# --------------------------------------------------------------------------
# F02 - the retained row must not keep a redeemable secret
# --------------------------------------------------------------------------


@pytest.mark.integration
async def test_delivered_message_no_longer_stores_the_raw_token(
    db_engine: AsyncEngine,
) -> None:
    """verification_tokens stores only a SHA-256 hash so a database leak yields
    nothing redeemable. An outbox row retained after delivery with the plaintext
    still in it hands that guarantee straight back."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _empty_the_queue(session_factory)

    async with session_factory() as session, session.begin():
        message = await EmailOutboxRepository(session).add(
            user_id=None,
            recipient_email=_unique_email(),
            template="verification_email",
            payload={"token": SECRET, "verification_url": f"https://x/verify?token={SECRET}"},
        )

    await outbox_job.dispatch_outbox({"session_factory": session_factory})

    async with session_factory() as session:
        row = await session.get(EmailOutboxModel, message.id)

    assert row is not None
    assert row.status == "sent"
    # Keys survive so the row still shows what was sent; values do not.
    assert set(row.payload) == {"token", "verification_url"}
    assert SECRET not in str(row.payload)
    assert row.payload["token"] == REDACTED


@pytest.mark.integration
async def test_permanently_failed_message_also_drops_the_raw_token(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed row is terminal and never retried, so its token is pure
    exposure with no remaining purpose."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _empty_the_queue(session_factory)

    async with session_factory() as session, session.begin():
        message = await EmailOutboxRepository(session).add(
            user_id=None,
            recipient_email=_unique_email(),
            template="verification_email",
            payload={"token": SECRET},
        )
        # One attempt short of the cap, so a single failure is terminal.
        await session.execute(
            update(EmailOutboxModel)
            .where(EmailOutboxModel.id == message.id)
            .values(attempt_count=4)
        )

    class Failing:
        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("provider is down")

    monkeypatch.setattr(outbox_job, "get_email_provider", lambda settings: Failing())
    await outbox_job.dispatch_outbox({"session_factory": session_factory})

    async with session_factory() as session:
        row = await session.get(EmailOutboxModel, message.id)

    assert row is not None
    assert row.status == "failed"
    assert SECRET not in str(row.payload)


# --------------------------------------------------------------------------
# F13 - the log line must not carry the secret either
# --------------------------------------------------------------------------


async def test_console_provider_does_not_log_token_or_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured logs are copied, shipped and retained far more widely than
    the database is.

    The module logger is replaced rather than reconfiguring structlog globally:
    configure_logging() sets cache_logger_on_first_use, so a logger already
    bound by an earlier test keeps its original processor chain and a global
    reconfigure here would silently capture nothing.
    """

    class _Recorder:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def ainfo(self, event: str, **kwargs: object) -> None:
            self.calls.append((event, kwargs))

    recorder = _Recorder()
    monkeypatch.setattr(console_module, "logger", recorder)

    await ConsoleEmailProvider().send(
        to="someone@example.com",
        template="verification_email",
        payload={"token": SECRET, "verification_url": f"https://x/verify?token={SECRET}"},
    )

    assert len(recorder.calls) == 1
    event, fields = recorder.calls[0]
    assert event == "console_email_send"
    assert SECRET not in str(fields)
    # Safe metadata is still present and useful.
    assert fields["to"] == "someone@example.com"
    assert fields["template"] == "verification_email"
    assert fields["payload_keys"] == ["token", "verification_url"]
    assert "payload" not in fields


# --------------------------------------------------------------------------
# F05 - one failure must not roll back unrelated successful messages
# --------------------------------------------------------------------------


@pytest.mark.integration
async def test_one_failing_message_does_not_undo_the_others(db_engine: AsyncEngine) -> None:
    """Previously every message shared one transaction, so a failure on the
    last one rolled back the persisted state of all the ones already sent and
    they were externally re-delivered on the next tick."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _empty_the_queue(session_factory)

    emails = [_unique_email() for _ in range(3)]
    async with session_factory() as session, session.begin():
        repo = EmailOutboxRepository(session)
        for address in emails:
            await repo.add(
                user_id=None,
                recipient_email=address,
                template="verification_email",
                payload={"token": SECRET},
            )

    doomed = emails[1]

    class FailsOnOne:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            self.sent.append(to)
            if to == doomed:
                raise RuntimeError("provider rejected this one")

    provider = FailsOnOne()
    monkey = pytest.MonkeyPatch()
    monkey.setattr(outbox_job, "get_email_provider", lambda settings: provider)
    try:
        await outbox_job.dispatch_outbox({"session_factory": session_factory})
    finally:
        monkey.undo()

    async with session_factory() as session:
        result = await session.scalars(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email.in_(emails))
        )
        rows = {str(row.recipient_email): row for row in result}

    assert rows[emails[0]].status == "sent"
    assert rows[emails[2]].status == "sent"
    # The failure is contained to its own message and recorded on it.
    assert rows[doomed].status == "pending"
    assert rows[doomed].attempt_count == 1
    assert rows[doomed].last_error is not None
    # Each message was offered to the provider exactly once.
    assert sorted(provider.sent) == sorted(emails)


@pytest.mark.integration
async def test_a_worker_killed_mid_batch_keeps_the_messages_it_already_delivered(
    db_engine: AsyncEngine,
) -> None:
    """The amplification the per-message transaction actually removes.

    The test above does not reach it. A provider error is caught inside the
    loop and turned into `mark_failed`, so nothing escapes and the batch-wide
    transaction still commits cleanly - it passes against the old code too.
    The batch-wide version only loses work when the transaction never commits
    at all, which happens when the process dies partway through the batch.

    `except Exception` in the job does not catch `BaseException`, so raising
    one models exactly that: the worker is killed after two messages have gone
    out over SMTP. Under one shared transaction their `sent` status is rolled
    back with everything else, and the next tick re-delivers mail the recipient
    has already received. Under a transaction per message they are already
    committed and stay sent.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _empty_the_queue(session_factory)

    emails = [_unique_email() for _ in range(3)]
    async with session_factory() as session, session.begin():
        repo = EmailOutboxRepository(session)
        for address in emails:
            await repo.add(
                user_id=None,
                recipient_email=address,
                template="verification_email",
                payload={"token": SECRET},
            )

    delivered: list[str] = []

    class DiesOnTheThird:
        async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
            if len(delivered) == 2:
                raise KeyboardInterrupt("worker killed")
            delivered.append(to)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(outbox_job, "get_email_provider", lambda settings: DiesOnTheThird())
    try:
        with pytest.raises(KeyboardInterrupt):
            await outbox_job.dispatch_outbox({"session_factory": session_factory})
    finally:
        monkey.undo()

    assert len(delivered) == 2, "the fixture must reach the provider twice before dying"

    async with session_factory() as session:
        result = await session.scalars(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email.in_(emails))
        )
        rows = {str(row.recipient_email): row for row in result}

    # Mail that actually went out stays recorded as sent, so the next tick does
    # not send it again.
    for address in delivered:
        assert rows[address].status == "sent", f"{address} was delivered but rolled back to pending"
    # And the one that never reached the provider is still queued.
    undelivered = set(emails) - set(delivered)
    assert len(undelivered) == 1
    assert rows[undelivered.pop()].status == "pending"


# --------------------------------------------------------------------------
# F12 - a bad provider name must fail loudly, not stall the queue silently
# --------------------------------------------------------------------------


def test_unknown_provider_name_raises_rather_than_returning_a_stub() -> None:
    from app.core.config import Settings

    settings = Settings(
        database_url="postgresql+asyncpg://x/x",
        redis_url="redis://x",
        jwt_signing_key="x",
        csrf_secret="x",
        ip_hash_salt="x",
        email_provider="definitely-invalid",
    )
    with pytest.raises(NotImplementedError):
        get_email_provider(settings)


async def test_worker_startup_rejects_an_invalid_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validated at startup so the container dies visibly. Resolving it inside
    dispatch_outbox instead aborted the job before a single row was claimed, so
    no message ever recorded an attempt or an error - the queue just stopped,
    indistinguishable from an idle one."""
    from app.core.config import get_settings

    monkeypatch.setenv("EMAIL_PROVIDER", "definitely-invalid")
    get_settings.cache_clear()
    try:
        from app.worker import on_startup

        with pytest.raises(NotImplementedError):
            await on_startup({})
    finally:
        monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
        get_settings.cache_clear()
