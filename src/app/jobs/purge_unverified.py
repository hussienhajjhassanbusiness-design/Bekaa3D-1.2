from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.identity.infrastructure.repositories import UserRepository
from app.platform.public import settings_reader

logger = structlog.get_logger()


async def purge_unverified_accounts(ctx: dict[str, Any]) -> int:
    """arq job: physically removes accounts that were never verified.

    FR-02 lists this under failure behaviour: an address that registers and
    never confirms leaves a row holding an email address indefinitely, which is
    personal data retained for no purpose. Verified accounts are never touched -
    those are anonymised through the account-deletion flow instead
    (database-design.md 5.1).

    The retention period is the `unverified_account_purge_period` setting
    (VS-007), read through the Platform settings service rather than from a
    source-code constant - BR-133 requires business parameters to be
    administrator-editable without a deployment.

    There is deliberately **no fallback**. If the setting is missing or its
    stored value is invalid, `SettingsReader` raises and this job fails visibly
    in the worker log and the cron-liveness alert. A `30` quietly substituted
    here would be the exact thing BR-133 forbids, and it would silently delete
    accounts on a schedule nobody had approved - the failure mode is worse than
    not running at all, because it is invisible.

    Read inside the same transaction as the delete, so the cutoff and the rows
    it selects come from one consistent snapshot.
    """
    session_factory = ctx["session_factory"]
    async with session_factory() as session, session.begin():
        retention_seconds = await settings_reader(session).get_duration_seconds(
            "unverified_account_purge_period"
        )
        cutoff = datetime.now(UTC) - timedelta(seconds=retention_seconds)
        purged = await UserRepository(session).purge_never_verified_before(cutoff)

    if purged:
        await logger.ainfo(
            "unverified_accounts_purged",
            count=purged,
            retention_seconds=retention_seconds,
        )
    return purged
