"""Daily check that rotates the IP-hash salt once per UTC month (SRS 23, SEC-25, ADR-028).

Runs daily and at worker start because arq skips missed ticks; the month rule and an
advisory lock make extra runs, on any number of workers, no-ops."""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.platform.application.commands.rotate_ip_hash_salt import RotateIpHashSalt
from app.platform.public import SqlAuditWriter, ip_hash_salt_store

logger = structlog.get_logger()


class IpHashSaltRotationError(RuntimeError):
    """Raised so arq marks the job failed; carries the error class only."""


async def rotate_ip_salt(ctx: dict[str, Any], *, now: datetime | None = None) -> bool:
    """arq job. True when it rotated; a failure rolls back and the next run retries."""
    try:
        async with ctx["session_factory"]() as session, session.begin():
            new_id = await RotateIpHashSalt(
                ip_hash_salt_store(session), SqlAuditWriter(session)
            ).execute(now=now or datetime.now(UTC))
    except (SQLAlchemyError, OSError) as exc:
        # The class only: a driver message can carry the statement and its values.
        await logger.awarning("ip_hash_salt_rotation_failed", error=type(exc).__name__)
        raise IpHashSaltRotationError(type(exc).__name__) from None

    if new_id is None:
        await logger.adebug("ip_hash_salt_rotation_not_due")
        return False
    await logger.ainfo("ip_hash_salt_rotated", salt_id=str(new_id))
    return True
