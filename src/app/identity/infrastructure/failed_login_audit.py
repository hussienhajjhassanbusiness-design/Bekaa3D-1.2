"""BR-132, ADR-050: a refused login's audit row, in a transaction of its own, because the
request's own transaction rolls back with the refusal."""

from datetime import timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identity.infrastructure.repositories import UserRepository
from app.platform.public import AuditLogRepository

ACTION = "user.login_failed"
WINDOW = timedelta(minutes=15)

logger = structlog.get_logger()


async def record_failed_login(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ip_hash: str | None,
    request_id: str | None,
    reason: str,
    email: str | None = None,
    user_id: UUID | None = None,
) -> None:
    """Never raises: an audit outage must not turn a 401 into a 500 (ADR-050). The attempted
    address is only looked up, never stored, so a typo or a pasted password stays out."""
    try:
        async with session_factory() as session, session.begin():
            if user_id is None and email is not None:
                user = await UserRepository(session).get_by_email(email)
                user_id = user.id if user is not None else None
            await AuditLogRepository(session).count_in_window(
                action=ACTION,
                entity_type="User",
                entity_id=user_id,
                ip_hash=ip_hash,
                request_id=request_id,
                reason=reason,
                window=WINDOW,
            )
    except Exception as exc:
        await logger.aerror("failed_login_audit_lost", reason=reason, error=type(exc).__name__)
