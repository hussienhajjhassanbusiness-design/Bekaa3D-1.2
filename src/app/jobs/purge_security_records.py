"""Daily purge of expired tokens and ended sessions past retention (VS-046, SRS 23).

Retention comes from two settings read with no fallback (BR-133). Each batch is its
own short transaction using SKIP LOCKED; a capped run logs truncated and resumes next day."""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.identity.application.commands.purge_expired_security_records import (
    PurgeExpiredSecurityRecords,
)
from app.identity.infrastructure.repositories import (
    PasswordResetTokenRepository,
    SessionRepository,
    VerificationTokenRepository,
)
from app.platform.public import settings_reader

logger = structlog.get_logger()

BATCH_SIZE = 1000
MAX_BATCHES_PER_RUN = 50


async def purge_expired_security_records(
    ctx: dict[str, Any],
    *,
    now: datetime | None = None,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES_PER_RUN,
) -> dict[str, int]:
    """arq job. Returns rows deleted per table, and `truncated` (0 or 1)."""
    session_factory = ctx["session_factory"]
    moment = now or datetime.now(UTC)
    async with session_factory() as session, session.begin():
        reader = settings_reader(session)
        token_retention = await reader.get_duration_seconds("security_token_retention_period")
        session_retention = await reader.get_duration_seconds("session_retention_period")
    token_cutoff = moment - timedelta(seconds=token_retention)
    session_cutoff = moment - timedelta(seconds=session_retention)

    totals = {"verification_tokens": 0, "password_reset_tokens": 0, "sessions": 0}
    truncated = True
    for _ in range(max_batches):
        async with session_factory() as session, session.begin():
            batch = await PurgeExpiredSecurityRecords(
                VerificationTokenRepository(session),
                PasswordResetTokenRepository(session),
                SessionRepository(session),
            ).execute_batch(
                token_cutoff=token_cutoff, session_cutoff=session_cutoff, limit=batch_size
            )
        counts = (batch.verification_tokens, batch.password_reset_tokens, batch.sessions)
        for key, count in zip(totals, counts, strict=True):
            totals[key] += count
        if max(counts) < batch_size:
            truncated = False
            break

    if any(totals.values()):
        await logger.ainfo(
            "security_records_purged",
            **totals,
            truncated=truncated,
            token_retention_seconds=token_retention,
            session_retention_seconds=session_retention,
        )
    return {**totals, "truncated": int(truncated)}
