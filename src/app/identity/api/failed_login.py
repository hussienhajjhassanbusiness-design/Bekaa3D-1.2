"""The refused-login audit, for the login and second-factor routes (ADR-050)."""

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip
from app.core.security import hash_ip
from app.identity.infrastructure.failed_login_audit import record_failed_login


async def audit_refused_login(
    request: Request,
    session: AsyncSession,
    *,
    reason: str,
    email: str | None = None,
    user_id: UUID | None = None,
) -> None:
    """Rolls the request back first: holding its connection while waiting for a second one
    would let a burst of bad logins deadlock the pool."""
    await session.rollback()
    ip = client_ip(request)
    await record_failed_login(
        request.app.state.db_session_factory,
        ip_hash=hash_ip(ip) if ip else None,
        request_id=getattr(request.state, "request_id", None),
        reason=reason,
        email=email,
        user_id=user_id,
    )
