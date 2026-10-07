from app.identity.application.ports import (
    PasswordResetTokenStore,
    UserStore,
)
from app.identity.application.security.password_hasher import perform_dummy_hash
from app.identity.application.services.password_reset import (
    issue_password_reset_email,
    reset_request_eligible,
)
from app.platform.application.ports.audit_writer import AuditWriter
from app.platform.application.ports.outbox_writer import OutboxWriter


class RequestPasswordReset:
    """Enumeration-safe per SRS §8.1 and api-endpoints.md §5: the caller always
    gets the same 202, whether the address is unknown, known and eligible, or
    known and still inside its cooldown. Every branch below returns None for
    that reason - there is nothing to report back that would not be an answer to
    "does this account exist?"."""

    def __init__(
        self,
        user_repo: UserStore,
        token_repo: PasswordResetTokenStore,
        outbox_repo: OutboxWriter,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._outbox = outbox_repo
        self._audit = audit_writer

    async def execute(self, *, email: str, request_id: str | None, ip_hash: str | None) -> None:
        # Exactly one Argon2id verification on every branch, so the expensive
        # work never depends on whether the account exists (BUG-04). The
        # database writes only the known branch makes are hidden by the
        # response-time floor (api/enumeration.py).
        await perform_dummy_hash()

        # Locked: concurrent requests for one account queue here, so only the
        # first passes the cooldown (BUG-17).
        user = await self._users.get_by_email_for_update(email)
        if user is None:
            return
        if not await reset_request_eligible(user=user, token_repo=self._tokens):
            return

        await issue_password_reset_email(
            user=user, token_repo=self._tokens, outbox_repo=self._outbox
        )
        # Audited even though the reset has not happened yet: a burst of these
        # against one account is what an account-takeover attempt looks like
        # from the inside, and the trail is worthless if it only starts once the
        # attacker succeeds.
        await self._audit.record(
            actor_user_id=user.id,
            action="user.password_reset_requested",
            entity_type="User",
            entity_id=user.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
