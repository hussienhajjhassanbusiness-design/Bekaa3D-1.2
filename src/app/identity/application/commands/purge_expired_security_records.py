from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.identity.application.ports import (
    PasswordResetTokenStore,
    SessionStore,
    VerificationTokenStore,
)


@dataclass(frozen=True)
class PurgeBatchResult:
    verification_tokens: int
    password_reset_tokens: int
    sessions: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PurgeExpiredSecurityRecords:
    """Delete ended sessions and expired tokens past their retention (VS-046, SEC-07).
    One batch per table per call; the caller loops and owns each transaction."""

    def __init__(
        self,
        verification_tokens: VerificationTokenStore,
        password_reset_tokens: PasswordResetTokenStore,
        sessions: SessionStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._verification_tokens = verification_tokens
        self._password_reset_tokens = password_reset_tokens
        self._sessions = sessions
        self._clock = clock

    async def execute_batch(
        self, *, token_cutoff: datetime, session_cutoff: datetime, limit: int
    ) -> PurgeBatchResult:
        """Refuses a cutoff at or after the wall clock: a live row must never match."""
        now = self._clock()
        if token_cutoff >= now or session_cutoff >= now:
            raise ValueError("purge cutoff must be in the past")
        return PurgeBatchResult(
            verification_tokens=await self._verification_tokens.delete_expired_batch(
                cutoff=token_cutoff, limit=limit
            ),
            password_reset_tokens=await self._password_reset_tokens.delete_expired_batch(
                cutoff=token_cutoff, limit=limit
            ),
            sessions=await self._sessions.delete_ended_batch(cutoff=session_cutoff, limit=limit),
        )
