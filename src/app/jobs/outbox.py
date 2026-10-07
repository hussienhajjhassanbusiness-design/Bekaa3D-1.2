from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.core.config import get_settings
from app.integrations.email.factory import get_email_provider
from app.platform.domain.enums import OutboxStatus
from app.platform.infrastructure.repositories import EmailOutboxRepository

logger = structlog.get_logger()

BATCH_SIZE = 20
RETRY_BASE_SECONDS = 60


async def dispatch_outbox(ctx: dict[str, Any]) -> int:
    """arq job: sends due, pending outbox emails. Scheduled every minute (SRS 23).

    Each message gets its own transaction. Sending inside a transaction is
    unavoidable - the provider call and the status write have to be tied
    together somehow - so a commit that fails after a successful send will
    re-deliver that message on the next tick. That at-least-once window is
    inherent and is not claimed to be closed here.

    What a per-message transaction does remove is the amplification: with the
    whole batch under one transaction, one failed commit rolled back up to
    BATCH_SIZE already-delivered messages and re-sent every one of them. The
    blast radius is now a single message.

    Concurrency safety still comes from the repository's SELECT ... FOR UPDATE
    SKIP LOCKED claim, which is unchanged - two workers still take disjoint
    messages, they just hold one row lock at a time instead of twenty.
    """
    session_factory = ctx["session_factory"]
    provider = get_email_provider(get_settings())

    processed = 0
    for _ in range(BATCH_SIZE):
        async with session_factory() as session, session.begin():
            repo = EmailOutboxRepository(session)
            claimed = await repo.claim_due(limit=1, now=datetime.now(UTC))
            if not claimed:
                return processed

            message = claimed[0]
            try:
                await provider.send(
                    to=message.recipient_email,
                    template=message.template,
                    payload=message.payload,
                )
            except Exception as exc:
                next_attempt = datetime.now(UTC) + timedelta(
                    seconds=RETRY_BASE_SECONDS * (2**message.attempt_count)
                )
                message.mark_failed(str(exc), next_attempt_at=next_attempt, at=datetime.now(UTC))
                if message.status == OutboxStatus.FAILED:
                    await logger.aerror(
                        "outbox_message_permanently_failed",
                        outbox_id=str(message.id),
                        attempts=message.attempt_count,
                    )
                else:
                    await logger.awarning(
                        "outbox_send_failed",
                        outbox_id=str(message.id),
                        attempt=message.attempt_count,
                        # The scrubbed text, never str(exc): see mark_failed.
                        error=message.last_error,
                    )
            else:
                message.mark_sent(datetime.now(UTC))
            await repo.save(message)
        processed += 1

    return processed
