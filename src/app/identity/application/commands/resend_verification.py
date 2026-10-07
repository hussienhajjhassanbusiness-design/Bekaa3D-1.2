from app.identity.application.ports import UserStore, VerificationTokenStore
from app.identity.application.security.password_hasher import perform_dummy_hash
from app.identity.application.services.verification import (
    issue_verification_email,
    resend_eligible,
)
from app.platform.application.ports.audit_writer import AuditWriter
from app.platform.application.ports.outbox_writer import OutboxWriter


class ResendVerification:
    """Uniform response regardless of account existence/state (SRS 8.1) - the
    caller never learns anything from this beyond "request accepted"."""

    def __init__(
        self,
        user_repo: UserStore,
        token_repo: VerificationTokenStore,
        outbox_repo: OutboxWriter,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._outbox = outbox_repo
        self._audit = audit_writer

    async def execute(
        self, *, email: str, request_id: str | None = None, ip_hash: str | None = None
    ) -> None:
        # Exactly one Argon2id verification on every branch - the issuing branch
        # included. The expensive work must not depend on the outcome: when it
        # ran only on the silent branches, a *fast* answer revealed an unverified
        # account (BUG-05). The database work that still differs between branches
        # is hidden by the response-time floor (api/enumeration.py).
        await perform_dummy_hash()

        # Locked: concurrent resends for one account queue here, so only the
        # first passes the cooldown (BUG-17).
        user = await self._users.get_by_email_for_update(email)
        if user is None or not (
            not user.is_verified and await resend_eligible(user=user, token_repo=self._tokens)
        ):
            # Unknown address, already verified, or still inside the cooldown.
            return

        await issue_verification_email(user=user, token_repo=self._tokens, outbox_repo=self._outbox)
        # BR-132 requires every auth event to be audit-logged, and SRS 22.4
        # classifies resend-verification as an authentication endpoint. Written
        # only when mail is actually issued: an audit row for a non-event would
        # be noise, and the row is server-side so it leaks nothing to the caller
        # either way.
        await self._audit.record(
            actor_user_id=user.id,
            action="user.verification_resent",
            entity_type="User",
            entity_id=user.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
