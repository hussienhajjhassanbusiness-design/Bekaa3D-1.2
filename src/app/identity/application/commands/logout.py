from datetime import UTC, datetime
from uuid import UUID

from app.identity.application.ports import SessionStore
from app.platform.application.ports.audit_writer import AuditWriter


class Logout:
    def __init__(self, session_repo: SessionStore, audit_writer: AuditWriter) -> None:
        self._sessions = session_repo
        self._audit = audit_writer

    async def execute(
        self, *, session_id: UUID, request_id: str | None, ip_hash: str | None
    ) -> None:
        """Idempotent by design: logging out of a session that is already gone
        or already revoked still succeeds, because the caller's goal - "this
        session must not work any more" - is satisfied either way."""
        session = await self._sessions.get_for_update(session_id)
        if session is None or session.is_revoked:
            return

        session.revoke(datetime.now(UTC))
        await self._sessions.save(session)
        await self._audit.record(
            actor_user_id=session.user_id,
            action="user.logged_out",
            entity_type="Session",
            entity_id=session.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
